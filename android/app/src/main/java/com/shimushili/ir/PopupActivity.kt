package com.shimushili.ir

import android.app.PendingIntent
import android.app.StatusBarManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.os.Build
import android.os.Bundle
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/** The remote that pops up from the Control Center tile. */
class PopupActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Device.init(this)
        setContent {
            AppTheme {
                val m = rememberRemoteModel()
                LaunchedEffect(Unit) { if (Device.configured) m.refresh() }
                Box(
                    Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.45f))
                        .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { finish() },
                ) {
                    Surface(
                        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
                        tonalElevation = 3.dp,
                        modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().heightIn(max = 760.dp)
                            .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) {},
                    ) {
                        Column(Modifier.verticalScroll(rememberScrollState()).navigationBarsPadding().padding(16.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("שלט", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                                IconButton(onClick = { openApp(null) }) { Icon(Icons.Filled.Settings, "הגדרות") }
                                IconButton(onClick = { finish() }) { Icon(Icons.Filled.Close, "סגור") }
                            }
                            if (!Device.configured) {
                                SetupCard("צריך להשלים התקנה באפליקציה", "פתח אפליקציה") { openApp(null) }
                            } else {
                                RemotePanel(m) { openApp(it) }
                            }
                        }
                    }
                }
            }
        }
    }

    private fun openApp(setup: String?) {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK).apply {
            if (setup != null) putExtra("setup", setup)
        })
        finish()
    }
}

/** Quick Settings ("Control Center") tile: tap = open the popup remote. */
class RemoteTileService : TileService() {
    override fun onStartListening() {
        qsTile?.apply {
            state = Tile.STATE_ACTIVE
            label = "שלט"
            updateTile()
        }
    }

    override fun onClick() {
        val intent = Intent(this, PopupActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val open = {
            if (Build.VERSION.SDK_INT >= 34) {
                startActivityAndCollapse(PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE))
            } else {
                @Suppress("DEPRECATION", "StartActivityAndCollapseDeprecated")
                startActivityAndCollapse(intent)
            }
        }
        if (isLocked) unlockAndRun { open() } else open()
    }
}

/** Android 13+: one-tap "add tile to Quick Settings" system prompt. */
fun requestTile(ctx: Context) {
    if (Build.VERSION.SDK_INT < 33) return
    val sbm = ctx.getSystemService(StatusBarManager::class.java)
    sbm.requestAddTileService(
        ComponentName(ctx, RemoteTileService::class.java), "שלט",
        Icon.createWithResource(ctx, R.drawable.ic_tile), ctx.mainExecutor,
    ) { result ->
        if (result == StatusBarManager.TILE_ADD_REQUEST_RESULT_TILE_ALREADY_ADDED)
            Toast.makeText(ctx, "האריח כבר נמצא במרכז הבקרה", Toast.LENGTH_SHORT).show()
    }
}
