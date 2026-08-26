"""Agent C5: OHLCV-only LSTM volatility and CNN bottom/rebound model."""

from __future__ import annotations

import hashlib
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
from kospi200_agent_c3.runner import CNNBottomModel, LSTMVolatilityModel, set_deterministic, target_frame, train_cutoff_before_calibration
from kospi200_agent_c_independent.runner import load_membership


SEQUENCE_FEATURES = (
    "open_gap_log", "high_from_open_log", "low_from_open_log", "close_from_open_log",
    "close_return_log", "volume_z20", "drawdown_20", "distance_to_low_20",
    "range_compression_5_20", "return_volatility_20",
)


def sequence_feature_frame(market: pd.DataFrame) -> pd.DataFrame:
    frame = market.sort_values(["ticker", "date"], kind="mergesort").copy()
    group = frame.groupby("ticker", sort=False)
    prior_close = group["close"].shift(1)
    share_ratio = frame["listed_shares"] / group["listed_shares"].shift(1)
    price_ratio = frame["close"] / prior_close
    frame["mechanical_reset"] = (
        (share_ratio > 0) & (price_ratio > 0)
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
    volume_mean = log_volume.groupby(frame["ticker"]).transform(lambda x: x.rolling(20, min_periods=20).mean())
    volume_std = log_volume.groupby(frame["ticker"]).transform(lambda x: x.rolling(20, min_periods=20).std())
    frame["volume_z20"] = (log_volume - volume_mean) / volume_std.replace(0, np.nan)
    rolling_high = group["close"].transform(lambda x: x.rolling(20, min_periods=20).max())
    rolling_low = group["low"].transform(lambda x: x.rolling(20, min_periods=20).min())
    frame["drawdown_20"] = frame["close"] / rolling_high - 1.0
    frame["distance_to_low_20"] = frame["close"] / rolling_low - 1.0
    true_range = (frame["high"] - frame["low"]) / prior_close
    range5 = true_range.groupby(frame["ticker"]).transform(lambda x: x.rolling(5, min_periods=5).mean())
    range20 = true_range.groupby(frame["ticker"]).transform(lambda x: x.rolling(20, min_periods=20).mean())
    frame["range_compression_5_20"] = range5 / range20.replace(0, np.nan)
    frame["return_volatility_20"] = frame["close_return_log"].groupby(frame["ticker"]).transform(
        lambda x: x.rolling(20, min_periods=20).std()
    )
    return frame[["date", "ticker", "mechanical_reset", *SEQUENCE_FEATURES]]


def build_sequences(features: pd.DataFrame, membership: pd.DataFrame, targets: pd.DataFrame,
                    sessions: list[str], start: str, end: str, lookback: int,
                    sample_every: int) -> tuple[np.ndarray, pd.DataFrame]:
    session_index = {day: i for i, day in enumerate(sessions)}
    panel = membership.merge(features, on=["date", "ticker"], how="left", validate="one_to_one")
    panel = panel.merge(targets, on=["date", "ticker"], how="left", validate="one_to_one")
    arrays: list[np.ndarray] = []; rows: list[dict[str, object]] = []
    target_columns = ("target_success_2to1", "target_volatility_10", "target_net_excess_10")
    for ticker, group in panel.groupby("ticker", sort=True):
        group = group.sort_values("date"); positions = group["date"].map(session_index).to_numpy(int)
        values = group[list(SEQUENCE_FEATURES)].to_numpy(np.float32)
        resets = group["mechanical_reset"].fillna(True).to_numpy(bool)
        dates = group["date"].to_numpy(str); target_values = group[list(target_columns)].to_numpy(float)
        for endpoint in range(lookback - 1, len(group)):
            day = dates[endpoint]
            if day < start or day > end or positions[endpoint] % sample_every != 0: continue
            window_start = endpoint - lookback + 1
            if not np.all(np.diff(positions[window_start:endpoint + 1]) == 1): continue
            if resets[window_start:endpoint + 1].any(): continue
            window = values[window_start:endpoint + 1]
            if not np.isfinite(window).all(): continue
            arrays.append(window)
            rows.append({"date": day, "ticker": ticker, **dict(zip(target_columns, target_values[endpoint], strict=True))})
    if not arrays: raise RuntimeError("Agent C5 유효 sequence가 없습니다.")
    return np.stack(arrays), pd.DataFrame(rows)


def train_pair(sequences: np.ndarray, target_volatility: np.ndarray, target_success: np.ndarray,
               config: dict, seed: int):
    set_deterministic(seed)
    valid = np.isfinite(target_volatility) & np.isfinite(target_success)
    raw_volatility = target_volatility[valid].astype(np.float32)
    volatility_mean = float(np.log1p(raw_volatility).mean())
    volatility_std = float(np.log1p(raw_volatility).std()) or 1.0
    x = torch.from_numpy(sequences[valid])
    y_vol = torch.from_numpy(((np.log1p(raw_volatility) - volatility_mean) / volatility_std).astype(np.float32))
    y_success = torch.from_numpy(target_success[valid].astype(np.float32))
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(TensorDataset(x, y_vol, y_success), batch_size=int(config["batch_size"]),
                        shuffle=True, generator=generator, num_workers=0)
    lstm = LSTMVolatilityModel(len(SEQUENCE_FEATURES), int(config["lstm_hidden_size"]))
    cnn = CNNBottomModel(len(SEQUENCE_FEATURES), int(config["cnn_channels"]))
    lstm_opt = torch.optim.AdamW(lstm.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]))
    cnn_opt = torch.optim.AdamW(cnn.parameters(), lr=float(config["learning_rate"]), weight_decay=float(config["weight_decay"]))
    vol_loss = nn.SmoothL1Loss(); positives = float(y_success.sum().item()); negatives = float(len(y_success) - positives)
    event_loss = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(negatives / max(positives, 1.0)))
    for _ in range(int(config["epochs"])):
        lstm.train(); cnn.train()
        for batch_x, batch_vol, batch_success in loader:
            lstm_opt.zero_grad(set_to_none=True); vol_loss(lstm(batch_x), batch_vol).backward(); lstm_opt.step()
            cnn_opt.zero_grad(set_to_none=True); event_loss(cnn(batch_x), batch_success).backward(); cnn_opt.step()
    return lstm, cnn, volatility_mean, volatility_std


def predict_pair(lstm, cnn, sequences: np.ndarray, mean: float, std: float, batch_size: int):
    lstm.eval(); cnn.eval(); vol_parts = []; prob_parts = []
    with torch.no_grad():
        for start in range(0, len(sequences), batch_size):
            batch = torch.from_numpy(sequences[start:start + batch_size])
            vol_parts.append(np.expm1(lstm(batch).numpy() * std + mean))
            prob_parts.append(torch.sigmoid(cnn(batch)).numpy())
    return np.concatenate(vol_parts), np.concatenate(prob_parts)


def score_with_weight(meta: pd.DataFrame, probability: np.ndarray, volatility: np.ndarray, weight: float) -> pd.DataFrame:
    scored = meta.copy(); scored["bottom_probability"] = probability
    scored["predicted_volatility"] = np.maximum(0.0, volatility)
    risk_rank = scored.groupby("date")["predicted_volatility"].rank(pct=True, method="average")
    scored["agent_c5_score"] = scored["bottom_probability"] - weight * risk_rank
    scored["agent_c5_rank"] = scored.groupby("date")["agent_c5_score"].rank(method="first", ascending=False)
    return scored


def choose_weight(meta: pd.DataFrame, probability: np.ndarray, volatility: np.ndarray, weights: list[float]) -> pd.DataFrame:
    valid_event = meta["target_success_2to1"].notna()
    auc = float(roc_auc_score(meta.loc[valid_event, "target_success_2to1"], probability[valid_event]))
    valid_vol = meta["target_volatility_10"].notna()
    vol_mae = float(mean_absolute_error(meta.loc[valid_vol, "target_volatility_10"], volatility[valid_vol]))
    rows = []
    for weight in weights:
        scored = score_with_weight(meta, probability, volatility, weight)
        correlations = [g["agent_c5_score"].corr(g["target_net_excess_10"], method="spearman")
                        for _, g in scored.dropna(subset=["target_net_excess_10"]).groupby("date")]
        rows.append({"risk_weight": weight, "mean_daily_excess_rank_ic": float(np.nanmean(correlations)), "bottom_auc": auc, "volatility_mae": vol_mae})
    return pd.DataFrame(rows).sort_values(["mean_daily_excess_rank_ic", "bottom_auc", "risk_weight"], ascending=[False, False, True]).reset_index(drop=True)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _write_gzip(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0}, float_format="%.12g", lineterminator="\n")


def _tree_hash(paths: list[Path], roots: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        root = next(item for item in roots if path.is_relative_to(item))
        digest.update(f"{root.name}/{path.relative_to(root).as_posix()}".encode()); digest.update(b"\0")
        digest.update(sha256(path).encode()); digest.update(b"\n")
    return digest.hexdigest()


def _state(model: nn.Module) -> dict[str, list]:
    return {name: tensor.detach().cpu().numpy().tolist() for name, tensor in sorted(model.state_dict().items())}


def run(config_path: Path, output_root: Path) -> dict[str, object]:
    guard_path(config_path); guard_path(output_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "v2-agent-c5-lstm-cnn-path-v1": raise ValueError("지원하지 않는 Agent C5 설정입니다.")
    if config.get("agent_b_access") is not False or config.get("portfolio_backtest") is not False or config.get("final_oos_access") is not False:
        raise ValueError("Agent C5는 Agent B·포트폴리오 backtest·Final OOS 접근을 금지합니다.")
    if torch.__version__.split("+")[0] != config["torch_version"]: raise RuntimeError("고정 PyTorch 버전 불일치")
    membership_root = Path(config["membership_root"]); market_roots = [Path(v) for v in config["market_roots"]]
    index_path = Path(config["index_file"])
    membership, membership_paths = load_membership(membership_root, config["market_start"], config["data_end"])
    market, sessions, market_paths = load_market_roots(market_roots, set(membership["ticker"]), int(config["market_start"][:4]), int(config["data_end"][:4]))
    index = load_official_index(index_path); features = sequence_feature_frame(market)
    targets = target_frame(market, index, sessions, 10, 0.05, 0.10, 0.004)
    train_x, train_meta = build_sequences(features, membership, targets, sessions, config["train_start"], config["train_end"], 40, 10)
    fit_cutoff = train_cutoff_before_calibration(sessions, config["calibration_start"], 10, 10)
    fit_valid = (train_meta["date"] <= fit_cutoff) & train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    calibration_valid = (train_meta["date"] >= config["calibration_start"]) & train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    if int(fit_valid.sum()) < int(config["minimum_train_sequences"]): raise RuntimeError("Agent C5 학습 sequence가 부족합니다.")
    lstm, cnn, mean, std = train_pair(train_x[fit_valid.to_numpy()], train_meta.loc[fit_valid, "target_volatility_10"].to_numpy(float), train_meta.loc[fit_valid, "target_success_2to1"].to_numpy(float), config, int(config["seed"]))
    cal_vol, cal_prob = predict_pair(lstm, cnn, train_x[calibration_valid.to_numpy()], mean, std, int(config["batch_size"]))
    weight_metrics = choose_weight(train_meta.loc[calibration_valid].reset_index(drop=True), cal_prob, cal_vol, [float(x) for x in config["risk_weight_grid"]])
    selected_weight = float(weight_metrics.iloc[0]["risk_weight"])
    final_valid = train_meta["target_volatility_10"].notna() & train_meta["target_success_2to1"].notna()
    final_lstm, final_cnn, final_mean, final_std = train_pair(train_x[final_valid.to_numpy()], train_meta.loc[final_valid, "target_volatility_10"].to_numpy(float), train_meta.loc[final_valid, "target_success_2to1"].to_numpy(float), config, int(config["seed"]))
    score_x, score_meta = build_sequences(features, membership, targets, sessions, config["score_start"], config["data_end"], 40, 1)
    predicted_vol, bottom_prob = predict_pair(final_lstm, final_cnn, score_x, final_mean, final_std, int(config["batch_size"]))
    scored = score_with_weight(score_meta, bottom_prob, predicted_vol, selected_weight)
    valid = scored.dropna(subset=["target_net_excess_10", "target_success_2to1", "target_volatility_10"])
    correlations = [g["agent_c5_score"].corr(g["target_net_excess_10"], method="spearman") for _, g in valid.groupby("date")]
    annual = valid.assign(year=valid["date"].str[:4]).groupby("year").apply(
        lambda f: float(np.nanmean([g["agent_c5_score"].corr(g["target_net_excess_10"], method="spearman") for _, g in f.groupby("date")])), include_groups=False)
    evaluation = {"mean_excess_rank_ic": float(np.nanmean(correlations)),
                  "bottom_auc": float(roc_auc_score(valid["target_success_2to1"], valid["bottom_probability"])),
                  "volatility_mae": float(mean_absolute_error(valid["target_volatility_10"], valid["predicted_volatility"])),
                  "positive_ic_years": int((annual > 0).sum()), "annual_ic": {str(k): float(v) for k, v in annual.items()}}
    output_root.mkdir(parents=True, exist_ok=False)
    weight_metrics.to_csv(output_root / "risk_weight_metrics.csv", index=False, float_format="%.12g", lineterminator="\n")
    _write_gzip(scored[["date", "ticker", "agent_c5_score", "agent_c5_rank", "bottom_probability", "predicted_volatility"]].sort_values(["date", "agent_c5_rank", "ticker"]), output_root / "daily_agent_c5_scores.csv.gz")
    _write_json(output_root / "evaluation.json", evaluation)
    _write_json(output_root / "selected_model.json", {"torch_version": torch.__version__.split("+")[0], "sequence_features": list(SEQUENCE_FEATURES), "lookback_sessions": 40, "selected_risk_weight": selected_weight, "volatility_log_mean": final_mean, "volatility_log_std": final_std, "lstm_state": _state(final_lstm), "cnn_state": _state(final_cnn)})
    _write_json(output_root / "data_audit.json", {"membership_rows_loaded": len(membership), "market_files_loaded": len(market_paths), "index_code": "1028", "train_sequence_rows": len(train_meta), "fit_cutoff": fit_cutoff, "fit_sequence_rows": int(fit_valid.sum()), "calibration_sequence_rows": int(calibration_valid.sum()), "score_sequence_rows": len(scored), "sequence_feature_count": len(SEQUENCE_FEATURES), "agent_b_accessed": False, "fundamental_data_accessed": False, "portfolio_backtest_run": False, "consumed_development_2022_2023_loaded": True, "final_oos_accessed": False})
    manifest = {"schema_version": "kospi200-agent-c5-lstm-cnn-path-v1", "experiment_id": config["experiment_id"], "status": "CONSUMED_DEVELOPMENT_DIAGNOSTIC_ONLY", "selected_risk_weight": selected_weight, "model_sha256": sha256(output_root / "selected_model.json"), "input_sha256": {"config": sha256(config_path), "official_index": sha256(index_path), "membership_tree": _tree_hash(membership_paths, [membership_root]), "market_tree": _tree_hash(market_paths, market_roots)}, "agent_b_accessed": False, "portfolio_backtest_run": False, "final_oos_accessed": False}
    for name in ("risk_weight_metrics.csv", "daily_agent_c5_scores.csv.gz", "selected_model.json", "evaluation.json", "data_audit.json"):
        manifest.setdefault("output_sha256", {})[name] = sha256(output_root / name)
    _write_json(output_root / "manifest.json", manifest)
    return manifest
