package com.projectpi.thermalalert

import android.annotation.SuppressLint
import android.app.Application
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.FlutterEngineCache
import io.flutter.embedding.engine.dart.DartExecutor
import io.flutter.plugin.common.MethodChannel

/**
 * Owns the Flutter engine instead of MainActivity, so the Dart isolate (and its alert
 * socket) keeps running when the activity is destroyed, e.g. swiped away from recents,
 * while MonitoringService keeps the process alive.
 */
class MainApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        val engine = FlutterEngine(this)
        engine.dartExecutor.executeDartEntrypoint(DartExecutor.DartEntrypoint.createDefault())
        MethodChannel(engine.dartExecutor.binaryMessenger, "project_pi/monitoring")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "start" -> {
                            // Starting a foreground service from the background throws on Android 12+;
                            // a retry while backgrounded only needs the service already running.
                            if (!MonitoringService.running) {
                                val intent = Intent(this, MonitoringService::class.java)
                                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                    startForegroundService(intent)
                                } else {
                                    startService(intent)
                                }
                            }
                            result.success(null)
                        }
                        "stop" -> {
                            stopService(Intent(this, MonitoringService::class.java))
                            result.success(null)
                        }
                        "requestBatteryExemption" -> result.success(requestBatteryExemption())
                        else -> result.notImplemented()
                    }
                } catch (error: Exception) {
                    result.error("monitoring", error.message, null)
                }
            }
        FlutterEngineCache.getInstance().put(ENGINE_ID, engine)
    }

    /** Returns true when the app is (already) exempt from battery optimisation. */
    @SuppressLint("BatteryLife") // sideloaded alarm app; Doze must not delay distress alerts
    private fun requestBatteryExemption(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        val power = getSystemService(Context.POWER_SERVICE) as PowerManager
        if (power.isIgnoringBatteryOptimizations(packageName)) return true
        startActivity(
            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                .setData(Uri.parse("package:$packageName"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
        return false
    }

    companion object {
        const val ENGINE_ID = "main"
    }
}
