# openWakeWord Models

Place the custom openWakeWord models used by the Pi keyword service here:

```text
tulong.onnx
tulong.onnx.data
help.onnx
help.onnx.data
save_me.onnx
save_me.onnx.data
help_me.onnx
help_me.onnx.data
please_help.onnx
please_help.onnx.data
```

The systemd service loads them from:

```text
/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

The keyword service automatically loads every `.onnx` file in this directory.
Keep each `.onnx.data` companion file beside its `.onnx` model. Companion data
files are not listed as models; ONNX Runtime reads them automatically.

Missing or unloadable models are skipped at startup, so you can copy trained
models into this directory incrementally. File names become the alert keyword
shown by the backend after underscores are converted to spaces.

Model training steps live in [`../README.md`](../README.md).
