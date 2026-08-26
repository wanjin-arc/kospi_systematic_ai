"""일봉 sequence에서 LSTM 변동성과 CNN 2:1 성공확률을 학습한다."""

from __future__ import annotations

import hashlib
import json
import random
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
from kospi200_agent_c_independent.runner import load_membership, trade_outcomes


SEQUENCE_FEATURES = (
    "open_gap_log", "high_from_open_log", "low_from_open_log",
    "close_from_open_log", "close_return_log", "volume_z20",
)


class LSTMVolatilityModel(nn.Module):
    def __init__(self, input_size: int, hidden_size: int):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        sequence, _ = self.lstm(values)
        return self.output(sequence[:, -1, :]).squeeze(-1)


class CNNBottomModel(nn.Module):
    def __init__(self, input_size: int, channels: int):
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv1d(input_size, channels, kernel_size=5),
            nn.ReLU(),
            nn.Conv1d(channels, channels, kernel_size=3),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.output = nn.Linear(channels, 1)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        features = self.network(values.transpose(1, 2)).squeeze(-1)
        return self.output(features).squeeze(-1)


def set_deterministic(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def sequence_feature_frame(market: pd.DataFrame) -> pd.DataFrame:
    frame = market.sort_values(["ticker", "date"]).copy()
    group = frame.groupby("ticker", sort=False)
    prior_close = group["close"].shift(1)
    share_ratio = frame["listed_shares"] / group["listed_shares"].shift(1)
    price_ratio = frame["close"] / prior_close
    frame["mechanical_reset"] = (
        (share_ratio > 0)
        & (price_ratio > 0)
        & (np.abs(np.log(share_ratio)) >= np.log(1.20))
        & (np.abs(np.log(share_ratio) + np.log(price_ratio)) <= np.log(1.15))
    )
    positive = (prior_close > 0) & (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
    frame["open_gap_log"] = np.where(positive, np.log(frame["open"] / prior_close), np.nan)
    frame["high_from_open_log"] = np.where(positive, np.log(frame["high"] / frame["open"]), np.nan)
    frame["low_from_open_log"] = np.where(positive, np.log(frame["low"] / frame["open"]), np.nan)
    frame["close_from_open_log"] = np.where(positive, np.log(frame["close"] / frame["open"]), np.nan)
    frame["close_return_log"] = np.where(positive, np.log(frame["close"] / prior_close), np.nan)
    log_volume = np.log1p(frame["volume"].clip(lower=0))
    volume_mean = log_volume.groupby(frame["ticker"]).transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    volume_std = log_volume.groupby(frame["ticker"]).transform(
        lambda values: values.rolling(20, min_periods=20).std()
    )
    frame["volume_z20"] = (log_volume - volume_mean) / volume_std.replace(0, np.nan)
    return frame[["date", "ticker", "mechanical_reset", *SEQUENCE_FEATURES]]


def target_frame(
    market: pd.DataFrame,
    index: pd.DataFrame,
    sessions: list[str],
    horizon: int,
    stop: float,
    take: float,
    cost: float,
) -> pd.DataFrame:
    outcomes = trade_outcomes(market, sessions, horizon, stop, take, cost)
    index_open = index.set_index("date")["open"].reindex(sessions)
    index_return = index_open.shift(-(horizon + 1)) / index_open.shift(-1) - 1.0
    index_return_by_date = dict(zip(sessions, index_return.to_numpy(float), strict=True))
    outcomes["target_net_excess_10"] = outcomes["target_terminal_net_return_10"] - outcomes["date"].map(index_return_by_date)
    volatility_parts = []
    for ticker, group in market.groupby("ticker", sort=True):
        close = group.set_index("date")["close"].reindex(sessions)
        daily_return = np.log(close / close.shift(1))
        future_volatility = daily_return.rolling(horizon, min_periods=horizon).std().shift(-horizon) * np.sqrt(252.0)
        volatility_parts.append(pd.DataFrame({
            "date": sessions,
            "ticker": ticker,
            "target_volatility_10": future_volatility.to_numpy(float),
        }))
    volatility = pd.concat(volatility_parts, ignore_index=True)
    return outcomes.merge(volatility, on=["date", "ticker"], how="left", validate="one_to_one")


def build_sequences(
    features: pd.DataFrame,
    membership: pd.DataFrame,
    targets: pd.DataFrame,
    sessions: list[str],
    start: str,
    end: str,
    lookback: int,
    sample_every: int,
) -> tuple[np.ndarray, pd.DataFrame]:
    session_index = {day: i for i, day in enumerate(sessions)}
    panel = membership.merge(features, on=["date", "ticker"], how="left", validate="one_to_one")
    panel = panel.merge(targets, on=["date", "ticker"], how="left", validate="one_to_one")
    arrays: list[np.ndarray] = []
    rows: list[dict[str, object]] = []
    target_columns = ("target_success_2to1", "target_volatility_10", "target_net_excess_10")
    for ticker, group in panel.groupby("ticker", sort=True):
        group = group.sort_values("date").copy()
        positions = group["date"].map(session_index).to_numpy(int)
        values = group[list(SEQUENCE_FEATURES)].to_numpy(np.float32)
        resets = group["mechanical_reset"].fillna(True).to_numpy(bool)
        dates = group["date"].to_numpy(str)
        target_values = group[list(target_columns)].to_numpy(float)
        for endpoint in range(lookback - 1, len(group)):
            day = dates[endpoint]
            if day < start or day > end or positions[endpoint] % sample_every != 0:
                continue
            window_start = endpoint - lookback + 1
            if not np.all(np.diff(positions[window_start:endpoint + 1]) == 1):
                continue
            if resets[window_start:endpoint + 1].any():
                continue
            window = values[window_start:endpoint + 1]
            if not np.isfinite(window).all():
                continue
            arrays.append(window)
            rows.append({
                "date": day,
                "ticker": ticker,
                **dict(zip(target_columns, target_values[endpoint], strict=True)),
            })
    if not arrays:
        return np.empty((0, lookback, len(SEQUENCE_FEATURES)), dtype=np.float32), pd.DataFrame(rows)
    return np.stack(arrays).astype(np.float32, copy=False), pd.DataFrame(rows)


def train_pair(
    sequences: np.ndarray,
    target_volatility: np.ndarray,
    target_success: np.ndarray,
    config: dict,
    seed: int,
) -> tuple[LSTMVolatilityModel, CNNBottomModel, float, float]:
    set_deterministic(seed)
    valid = np.isfinite(target_volatility) & np.isfinite(target_success)
    x = torch.from_numpy(sequences[valid])
    raw_volatility = target_volatility[valid].astype(np.float32)
    volatility_mean = float(np.mean(np.log1p(raw_volatility)))
    volatility_std = float(np.std(np.log1p(raw_volatility))) or 1.0
    y_vol = torch.from_numpy(((np.log1p(raw_volatility) - volatility_mean) / volatility_std).astype(np.float32))
    y_success = torch.from_numpy(target_success[valid].astype(np.float32))
    dataset = TensorDataset(x, y_vol, y_success)
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        dataset, batch_size=int(config["batch_size"]), shuffle=True,
        generator=generator, num_workers=0, drop_last=False,
    )
    lstm = LSTMVolatilityModel(len(SEQUENCE_FEATURES), int(config["lstm_hidden_size"]))
    cnn = CNNBottomModel(len(SEQUENCE_FEATURES), int(config["cnn_channels"]))
    lstm_optimizer = torch.optim.AdamW(lstm.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]))
    cnn_optimizer = torch.optim.AdamW(cnn.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]))
    volatility_loss = nn.SmoothL1Loss()
    positives = float(y_success.sum().item())
    negatives = float(len(y_success) - positives)
    event_loss = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives / max(positives, 1.0)))
    for _ in range(int(config["epochs"])):
        lstm.train(); cnn.train()
        for batch_x, batch_volatility, batch_success in loader:
            lstm_optimizer.zero_grad(set_to_none=True)
            volatility_loss(lstm(batch_x), batch_volatility).backward()
            lstm_optimizer.step()
            cnn_optimizer.zero_grad(set_to_none=True)
            event_loss(cnn(batch_x), batch_success).backward()
            cnn_optimizer.step()
    return lstm, cnn, volatility_mean, volatility_std


def predict_pair(
    lstm: LSTMVolatilityModel,
    cnn: CNNBottomModel,
    sequences: np.ndarray,
    volatility_mean: float,
    volatility_std: float,
    batch_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    lstm.eval(); cnn.eval()
    volatility_parts, probability_parts = [], []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            batch = torch.from_numpy(sequences[start:start + batch_size])
            normalized_volatility = lstm(batch).numpy()
            volatility_parts.append(np.expm1(normalized_volatility * volatility_std + volatility_mean))
            probability_parts.append(torch.sigmoid(cnn(batch)).numpy())
    return np.concatenate(volatility_parts), np.concatenate(probability_parts)


def score_with_weight(meta: pd.DataFrame, probability: np.ndarray, volatility: np.ndarray, weight: float) -> pd.DataFrame:
    scored = meta.copy()
    scored["bottom_probability"] = probability
    scored["predicted_volatility"] = np.maximum(0.0, volatility)
    risk_rank = scored.groupby("date")["predicted_volatility"].rank(pct=True, method="average")
    scored["agent_c3_score"] = scored["bottom_probability"] - weight * risk_rank
    scored["agent_c3_rank"] = scored.groupby("date")["agent_c3_score"].rank(method="first", ascending=False)
    return scored


def choose_weight(meta: pd.DataFrame, probability: np.ndarray, volatility: np.ndarray, weights: list[float]) -> pd.DataFrame:
    rows = []
    valid_event = meta["target_success_2to1"].notna()
    auc = float(roc_auc_score(meta.loc[valid_event, "target_success_2to1"], probability[valid_event]))
    volatility_valid = meta["target_volatility_10"].notna()
    vol_mae = float(mean_absolute_error(meta.loc[volatility_valid, "target_volatility_10"], volatility[volatility_valid]))
    for weight in weights:
        scored = score_with_weight(meta, probability, volatility, float(weight))
        correlations = [
            group["agent_c3_score"].corr(group["target_net_excess_10"], method="spearman")
            for _, group in scored.dropna(subset=["target_net_excess_10"]).groupby("date")
        ]
        rows.append({
            "risk_weight": float(weight),
            "mean_daily_excess_rank_ic": float(np.nanmean(correlations)),
            "bottom_auc": auc,
            "volatility_mae": vol_mae,
        })
    return pd.DataFrame(rows).sort_values(
        ["mean_daily_excess_rank_ic", "bottom_auc", "risk_weight"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def train_cutoff_before_calibration(sessions: list[str], calibration_start: str, purge: int, embargo: int) -> str:
    validation_index = next((i for i, day in enumerate(sessions) if day >= calibration_start), None)
    if validation_index is None:
        raise ValueError("Agent C3 calibration 시작 세션이 없습니다.")
    cutoff_index = validation_index - purge - embargo - 1
    if cutoff_index < 0:
        raise ValueError("Agent C3 purge·embargo 이전 학습 세션이 부족합니다.")
    return sessions[cutoff_index]


def _state(model: nn.Module) -> dict[str, list]:
    return {name: tensor.detach().cpu().numpy().tolist() for name, tensor in sorted(model.state_dict().items())}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], roots: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        root = next(item for item in roots if path.is_relative_to(item))
        digest.update(f"{root.name}/{path.relative_to(root).as_posix()}".encode())
        digest.update(b"\0"); digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("agent_b_access") is not False or config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent C3는 Agent B·포트폴리오·Final OOS 접근을 금지합니다.")
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
        float(config["stop_loss_rate"]), float(config["take_profit_rate"]),
        float(config["roundtrip_cost_rate"]),
    )
    train_x, train_meta = build_sequences(
        features, membership, targets, sessions, config["train_start"], config["train_end"],
        int(config["lookback_sessions"]), int(config["train_sample_every_sessions"]),
    )
    calibration_start = config["calibration_start"]
    fit_cutoff = train_cutoff_before_calibration(
        sessions, calibration_start, int(config["purge_sessions"]), int(config["embargo_sessions"])
    )
    calibration_mask = train_meta["date"] >= calibration_start
    fit_mask = train_meta["date"] <= fit_cutoff
    fit_valid = fit_mask & train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    calibration_valid = calibration_mask & train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    if int(fit_valid.sum()) < int(config["minimum_train_sequences"]):
        raise RuntimeError("Agent C3 학습 sequence가 부족합니다.")
    lstm, cnn, vol_mean, vol_std = train_pair(
        train_x[fit_valid.to_numpy()], train_meta.loc[fit_valid, "target_volatility_10"].to_numpy(float),
        train_meta.loc[fit_valid, "target_success_2to1"].to_numpy(float), config, int(config["seed"]),
    )
    calibration_vol, calibration_probability = predict_pair(
        lstm, cnn, train_x[calibration_valid.to_numpy()], vol_mean, vol_std, int(config["batch_size"]),
    )
    calibration_meta = train_meta.loc[calibration_valid].reset_index(drop=True)
    weight_metrics = choose_weight(
        calibration_meta, calibration_probability, calibration_vol,
        [float(value) for value in config["risk_weight_grid"]],
    )
    selected_weight = float(weight_metrics.iloc[0]["risk_weight"])

    final_valid = train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    final_lstm, final_cnn, final_vol_mean, final_vol_std = train_pair(
        train_x[final_valid.to_numpy()], train_meta.loc[final_valid, "target_volatility_10"].to_numpy(float),
        train_meta.loc[final_valid, "target_success_2to1"].to_numpy(float), config, int(config["seed"]),
    )
    score_x, score_meta = build_sequences(
        features, membership, targets, sessions, config["score_start"], config["data_end"],
        int(config["lookback_sessions"]), 1,
    )
    predicted_volatility, bottom_probability = predict_pair(
        final_lstm, final_cnn, score_x, final_vol_mean, final_vol_std, int(config["batch_size"]),
    )
    scored = score_with_weight(score_meta, bottom_probability, predicted_volatility, selected_weight)
    valid_eval = scored.dropna(subset=["target_net_excess_10", "target_success_2to1", "target_volatility_10"])
    correlations = [
        group["agent_c3_score"].corr(group["target_net_excess_10"], method="spearman")
        for _, group in valid_eval.groupby("date")
    ]
    annual_ic = valid_eval.assign(year=valid_eval["date"].str[:4]).groupby("year").apply(
        lambda frame: float(np.nanmean([
            group["agent_c3_score"].corr(group["target_net_excess_10"], method="spearman")
            for _, group in frame.groupby("date")
        ])), include_groups=False,
    )
    evaluation = {
        "mean_excess_rank_ic": float(np.nanmean(correlations)),
        "bottom_auc": float(roc_auc_score(valid_eval["target_success_2to1"], valid_eval["bottom_probability"])),
        "volatility_mae": float(mean_absolute_error(valid_eval["target_volatility_10"], valid_eval["predicted_volatility"])),
        "positive_ic_years": int((annual_ic > 0).sum()),
        "annual_ic": {str(year): float(value) for year, value in annual_ic.items()},
    }

    output_root.mkdir(parents=True, exist_ok=False)
    weight_metrics.to_csv(output_root / "risk_weight_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    columns = ["date", "ticker", "agent_c3_score", "agent_c3_rank", "bottom_probability", "predicted_volatility"]
    _write_gzip(scored[columns].sort_values(["date", "agent_c3_rank", "ticker"]), output_root / "daily_agent_c3_scores.csv.gz")
    model_state = {
        "torch_version": torch.__version__.split("+")[0],
        "sequence_features": list(SEQUENCE_FEATURES),
        "lookback_sessions": config["lookback_sessions"],
        "selected_risk_weight": selected_weight,
        "volatility_log_mean": final_vol_mean,
        "volatility_log_std": final_vol_std,
        "lstm_state": _state(final_lstm),
        "cnn_state": _state(final_cnn),
    }
    _write_json(output_root / "selected_model.json", model_state)
    _write_json(output_root / "evaluation.json", evaluation)
    audit = {
        "membership_rows_loaded": len(membership), "market_files_loaded": len(market_paths),
        "index_rows_loaded": len(index), "index_code": "1028", "train_sequence_rows": len(train_meta),
        "calibration_fit_cutoff": fit_cutoff, "purge_sessions": int(config["purge_sessions"]),
        "embargo_sessions": int(config["embargo_sessions"]),
        "fit_sequence_rows": int(fit_valid.sum()), "calibration_sequence_rows": int(calibration_valid.sum()),
        "score_sequence_rows": len(scored), "lookback_sessions": int(config["lookback_sessions"]),
        "sequence_feature_count": len(SEQUENCE_FEATURES), "agent_b_accessed": False,
        "fundamental_data_accessed": False, "portfolio_backtest_run": False,
        "v2_consumed_development_2022_2023_loaded": True,
        "legacy_v1_development_test_partition_accessed": False, "final_oos_accessed": False,
    }
    _write_json(output_root / "data_audit.json", audit)
    manifest = {
        "schema_version": "kospi200-agent-c3-lstm-cnn-v1", "experiment_id": config["experiment_id"],
        "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "selected_risk_weight": selected_weight,
        "model_sha256": sha256(output_root / "selected_model.json"),
        "input_sha256": {
            "config": sha256(config_path), "official_index": sha256(index_path),
            "membership_tree": _tree_hash(membership_paths, [membership_root]),
            "market_tree": _tree_hash(market_paths, market_roots),
        },
        "agent_b_accessed": False, "portfolio_backtest_run": False, "final_oos_accessed": False,
    }
    for name in ("risk_weight_metrics.csv", "daily_agent_c3_scores.csv.gz", "selected_model.json", "evaluation.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
