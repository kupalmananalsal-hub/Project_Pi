package com.projectpi.thermalalert

import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    // Attach to the engine MainApplication owns; a cached engine is not destroyed with the activity.
    override fun getCachedEngineId(): String = MainApplication.ENGINE_ID
}
