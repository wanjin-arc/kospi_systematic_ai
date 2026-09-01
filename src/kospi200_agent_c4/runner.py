"""LSTM·CNN 공동 표현으로 10거래일 공식 KOSPI200 초과수익을 직접 예측한다."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from kospi200_agent_b2.runner import load_official_index
from kospi200_agent_c.runner import guard_path, sha256
from kospi200_agent_c2.runner import load_market_roots
from kospi200_agent_c3.runner import (
    SEQUENCE_FEATURES,
    _tree_hash,
    _write_gzip,
    _write_json,
    build_sequences,
    sequence_feature_frame,
    set_deterministic,
    target_frame,
    train_cutoff_before_calibration,
)
from kospi200_agent_c_independent.runner import load_membership


class TemporalAlphaModel(nn.Module):
    """LSTM의 경로 기억과 CNN의 국소 패턴을 결합한 두 개 출력 head."""

    def __init__(self, input_size: int, hidden_size: int, channels: int):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.cnn = nn.Sequential(
            nn.Conv1d(input_size, channels, kernel_size=5), nn.ReLU(),
            nn.Conv1d(channels, channels, kernel_size=3), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.shared = nn.Sequential(nn.Linear(hidden_size + channels, hidden_size), nn.ReLU())
        self.excess_head = nn.Linear(hidden_size, 1)
        self.positive_head = nn.Linear(hidden_size, 1)

    def forward(self, values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        recurrent, _ = self.lstm(values)
        local = self.cnn(values.transpose(1, 2)).squeeze(-1)
        shared = self.shared(torch.cat([recurrent[:, -1, :], local], dim=1))
        return self.excess_head(shared).squeeze(-1), self.positive_head(shared).squeeze(-1)


def train_model(
    sequences: np.ndarray,
    target_excess: np.ndarray,
    config: dict,
    seed: int,
) -> tuple[TemporalAlphaModel, float, float]:
    set_deterministic(seed)
    valid = np.isfinite(target_excess)
    values = target_excess[valid].astype(np.float32)
    mean = float(values.mean())
    std = float(values.std()) or 1.0
    x = torch.from_numpy(sequences[valid])
    y = torch.from_numpy(((values - mean) / std).astype(np.float32))
    positive = torch.from_numpy((values > 0.0).astype(np.float32))
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        TensorDataset(x, y, positive), batch_size=int(config["batch_size"]),
        shuffle=True, generator=generator, num_workers=0,
    )
    model = TemporalAlphaModel(
        len(SEQUENCE_FEATURES), int(config["lstm_hidden_size"]), int(config["cnn_channels"])
    )
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"])
    )
    regression_loss = nn.SmoothL1Loss()
    positives = float(positive.sum().item())
    negatives = float(len(positive) - positives)
    classification_loss = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives / max(positives, 1.0)))
    classification_weight = float(config["classification_loss_weight"])
    for _ in range(int(config["epochs"])):
        model.train()
        for batch_x, batch_y, batch_positive in loader:
            optimizer.zero_grad(set_to_none=True)
            predicted, logit = model(batch_x)
            loss = regression_loss(predicted, batch_y) + classification_weight * classification_loss(logit, batch_positive)
            loss.backward()
            optimizer.step()
    return model, mean, std


def predict_model(
    model: TemporalAlphaModel,
    sequences: np.ndarray,
    target_mean: float,
    target_std: float,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    excess_parts, probability_parts = [], []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            normalized, logit = model(torch.from_numpy(sequences[start:start + batch_size]))
            excess_parts.append(normalized.numpy() * target_std + target_mean)
            probability_parts.append(torch.sigmoid(logit).numpy())
    return np.concatenate(excess_parts), np.concatenate(probability_parts)


def score_predictions(meta: pd.DataFrame, predicted_excess: np.ndarray, probability: np.ndarray, weight: float) -> pd.DataFrame:
    scored = meta.copy()
    scored["predicted_net_excess_10"] = predicted_excess
    scored["positive_excess_probability"] = probability
    excess_rank = scored.groupby("date")["predicted_net_excess_10"].rank(pct=True, method="average")
    probability_rank = scored.groupby("date")["positive_excess_probability"].rank(pct=True, method="average")
    scored["agent_c4_score"] = excess_rank + float(weight) * probability_rank
    scored["agent_c4_rank"] = scored.groupby("date")["agent_c4_score"].rank(method="first", ascending=False)
    return scored


def _state(model: nn.Module) -> dict[str, list]:
    return {name: tensor.detach().cpu().numpy().tolist() for name, tensor in sorted(model.state_dict().items())}


def evaluate(scored: pd.DataFrame) -> dict[str, object]:
    valid = scored.dropna(subset=["target_net_excess_10"])
    correlations = [
        group["agent_c4_score"].corr(group["target_net_excess_10"], method="spearman")
        for _, group in valid.groupby("date")
    ]
    annual = valid.assign(year=valid["date"].str[:4]).groupby("year").apply(
        lambda frame: float(np.nanmean([
            group["agent_c4_score"].corr(group["target_net_excess_10"], method="spearman")
            for _, group in frame.groupby("date")
        ])), include_groups=False,
    )
    truth = (valid["target_net_excess_10"] > 0).astype(int)
    return {
        "mean_excess_rank_ic": float(np.nanmean(correlations)),
        "positive_excess_auc": float(roc_auc_score(truth, valid["positive_excess_probability"])),
        "excess_mae": float(mean_absolute_error(valid["target_net_excess_10"], valid["predicted_net_excess_10"])),
        "positive_ic_years": int((annual > 0).sum()),
        "annual_ic": {str(year): float(value) for year, value in annual.items()},
    }


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("agent_b_access") is not False or config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent C4는 Agent B·포트폴리오·Final OOS 접근을 금지합니다.")
    if torch.__version__.split("+")[0] != config["torch_version"]:
        raise RuntimeError(f"동결 PyTorch 버전 불일치: {torch.__version__}")
    membership_root = Path(config["membership_root"])
    market_roots = [Path(value) for value in config["market_roots"]]
    index_path = Path(config["index_file"])
    membership, membership_paths = load_membership(membership_root, config["market_start"], config["data_end"])
    market, sessions, market_paths = load_market_roots(
        market_roots, set(membership["ticker"]), int(config["market_start"][:4]), int(config["data_end"][:4])
    )
    index = load_official_index(index_path)
    features = sequence_feature_frame(market)
    targets = target_frame(
        market, index, sessions, int(config["target_horizon_sessions"]),
        float(config["reference_stop_loss_rate"]), float(config["reference_take_profit_rate"]),
        float(config["roundtrip_cost_rate"]),
    )
    train_x, train_meta = build_sequences(
        features, membership, targets, sessions, config["train_start"], config["train_end"],
        int(config["lookback_sessions"]), int(config["train_sample_every_sessions"]),
    )
    fit_cutoff = train_cutoff_before_calibration(
        sessions, config["calibration_start"], int(config["purge_sessions"]), int(config["embargo_sessions"])
    )
    fit_mask = (train_meta["date"] <= fit_cutoff) & train_meta["target_net_excess_10"].notna()
    calibration_mask = (train_meta["date"] >= config["calibration_start"]) & train_meta["target_net_excess_10"].notna()
    if int(fit_mask.sum()) < int(config["minimum_train_sequences"]):
        raise RuntimeError("Agent C4 학습 sequence가 부족합니다.")
    calibration_model, target_mean, target_std = train_model(
        train_x[fit_mask.to_numpy()], train_meta.loc[fit_mask, "target_net_excess_10"].to_numpy(float), config, int(config["seed"])
    )
    calibration_excess, calibration_probability = predict_model(
        calibration_model, train_x[calibration_mask.to_numpy()], target_mean, target_std, int(config["batch_size"])
    )
    calibration_scored = score_predictions(
        train_meta.loc[calibration_mask].reset_index(drop=True), calibration_excess, calibration_probability,
        float(config["probability_rank_weight"]),
    )
    calibration_evaluation = evaluate(calibration_scored)
    final_mask = train_meta["target_net_excess_10"].notna()
    final_model, final_mean, final_std = train_model(
        train_x[final_mask.to_numpy()], train_meta.loc[final_mask, "target_net_excess_10"].to_numpy(float), config, int(config["seed"])
    )
    score_x, score_meta = build_sequences(
        features, membership, targets, sessions, config["score_start"], config["data_end"],
        int(config["lookback_sessions"]), 1,
    )
    predicted_excess, probability = predict_model(final_model, score_x, final_mean, final_std, int(config["batch_size"]))
    scored = score_predictions(score_meta, predicted_excess, probability, float(config["probability_rank_weight"]))
    evaluation = evaluate(scored)
    output_root.mkdir(parents=True, exist_ok=False)
    _write_gzip(
        scored[["date", "ticker", "agent_c4_score", "agent_c4_rank", "predicted_net_excess_10", "positive_excess_probability"]]
        .sort_values(["date", "agent_c4_rank", "ticker"]),
        output_root / "daily_agent_c4_scores.csv.gz",
    )
    _write_json(output_root / "calibration_evaluation.json", calibration_evaluation)
    _write_json(output_root / "evaluation.json", evaluation)
    _write_json(output_root / "selected_model.json", {
        "torch_version": torch.__version__.split("+")[0], "sequence_features": list(SEQUENCE_FEATURES),
        "lookback_sessions": int(config["lookback_sessions"]), "target_mean": final_mean, "target_std": final_std,
        "probability_rank_weight": float(config["probability_rank_weight"]), "state": _state(final_model),
    })
    audit = {
        "membership_rows_loaded": len(membership), "market_files_loaded": len(market_paths), "index_rows_loaded": len(index),
        "index_code": "1028", "train_sequence_rows": len(train_meta), "fit_cutoff": fit_cutoff,
        "fit_sequence_rows": int(fit_mask.sum()), "calibration_sequence_rows": int(calibration_mask.sum()),
        "score_sequence_rows": len(scored), "purge_sessions": int(config["purge_sessions"]),
        "embargo_sessions": int(config["embargo_sessions"]), "agent_b_accessed": False,
        "portfolio_backtest_run": False, "v2_consumed_development_2022_2023_loaded": True,
        "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False,
    }
    _write_json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-c4-temporal-alpha-v1", "experiment_id": config["experiment_id"],
        "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "input_sha256": {
            "config": sha256(config_path), "official_index": sha256(index_path),
            "membership_tree": _tree_hash(membership_paths, [membership_root]),
            "market_tree": _tree_hash(market_paths, market_roots),
        }, "model_sha256": sha256(output_root / "selected_model.json"),
        "agent_b_accessed": False, "portfolio_backtest_run": False, "final_oos_accessed": False,
    }
    for name in ("daily_agent_c4_scores.csv.gz", "calibration_evaluation.json", "evaluation.json", "selected_model.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
