# openWakeWord Models

Place the custom openWakeWord models used by the Pi keyword service here:

```text
tulong.tflite
help.tflite
save_me.tflite
help_me.tflite
please_help.tflite
i_need_help.tflite
somebody_help.tflite
call_ambulance.tflite
emergency.tflite
saklolo.tflite
tulungan_niyo_ako.tflite
tulungan_mo_ako.tflite
tulungan_ako.tflite
kailangan_ko_ng_tulong.tflite
iligtas_niyo_ako.tflite
may_emergency.tflite
```

The systemd service loads them from:

```text
/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

Missing model files are skipped at startup, so you can copy trained models into
this directory incrementally. File names become the alert keyword shown by the
backend after underscores are converted to spaces.

Model training steps live in [`../README.md`](../README.md).
