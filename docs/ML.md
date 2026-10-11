# Forecasting & ML status

**Implemented (tested on synthetic data):** persistence + damped-trend baseline for +1/+3/+6 h; qualitative bands from a heuristic, **uncalibrated** spread (`interval_method: heuristic_uncalibrated`); confidence capped at `medium`; no numeric probabilities are produced.

**NOT implemented: the XGBoost/LightGBM residual model.** There is no real labelled history in this repository, and training on the synthetic fixture would produce meaningless "accuracy". Nothing in the repo claims model skill.

Plan to add it honestly (SRS 8.4/16):
1. Obtain real gauge + rainfall history for >= several flood seasons (CWC/DHM agreement or downloadable bulletins).
2. Build features in `floodres/features.py` (rolling rain, slope, lags); train residual = observed - baseline, per horizon.
3. Rolling-origin validation (never random splits); report MAE/RMSE plus POD, false-alarm rate, CSI, lead time vs persistence (and GloFAS/official where available), separately for normal vs high-flow.
4. Conformal/quantile intervals; publish empirical coverage; only then relax the `medium` confidence ceiling.
5. Store artifacts under `s3://<bucket>/models/<version>/` with commit + training cutoff in `model_registry`; promote explicitly.
