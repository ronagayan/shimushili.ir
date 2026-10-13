package com.shimushili.ir

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val RELEASE = "https://github.com/ronagayan/shimushili.ir/releases/download/android-latest/"

/** Newer build available on the release page? Returns its versionCode or null. */
suspend fun newerVersion(ctx: Context): Long? = withContext(Dispatchers.IO) {
    runCatching {
        val c = URL(RELEASE + "version.json").openConnection() as HttpURLConnection
        c.connectTimeout = 6000; c.readTimeout = 6000; c.instanceFollowRedirects = true
        val latest = c.inputStream.bufferedReader().use { JSONObject(it.readText()).getLong("versionCode") }
        val info = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        @Suppress("DEPRECATION")
        val mine = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
        if (latest > mine) latest else null
    }.getOrNull()
}

@Composable
fun UpdateBanner() {
    val ctx = LocalContext.current
    var newer by remember { mutableStateOf<Long?>(null) }
    LaunchedEffect(Unit) { newer = newerVersion(ctx) }
    if (newer == null) return
    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("גרסה חדשה של האפליקציה זמינה", Modifier.weight(1f))
            Button(onClick = { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(RELEASE + "shimushili-remote.apk"))) }) { Text("עדכן") }
        }
    }
}
