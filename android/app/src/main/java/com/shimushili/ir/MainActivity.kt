@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.shimushili.ir

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Device.init(this)
        enableEdgeToEdge()
        val setup = intent.getStringExtra("setup")
        setContent { AppTheme { Surface(Modifier.fillMaxSize()) { MainScreen(setup) } } }
    }
}

@Composable
fun MainScreen(initialSetup: String?) {
    var screen by remember {
        mutableStateOf(if (!Device.configured) "onboard" else if (initialSetup != null) "setup_$initialSetup" else "remote")
    }
    if (screen != "remote" && screen != "onboard") BackHandler { screen = "remote" }
    Box(Modifier.fillMaxSize().systemBarsPadding()) {
        when (screen) {
            "onboard" -> Onboarding { screen = "remote" }
            "setup_ac" -> AcSetup { screen = "remote" }
            "setup_tv" -> TvSetup { screen = "remote" }
            "learn_tv" -> { RemoteHome({}, {}); LearnDialog("לימוד שלט הטלוויזיה", tvLearnAll()) { screen = "remote" } }
            "tile" -> TileStep { screen = "remote" }
            "settings" -> SettingsScreen(onBack = { screen = "remote" }, onNav = { screen = it })
            else -> RemoteHome(onSettings = { screen = "settings" }, onSetup = { screen = "setup_$it" })
        }
    }
}

@Composable
fun RemoteHome(onSettings: () -> Unit, onSetup: (String) -> Unit) {
    val m = rememberRemoteModel()
    LaunchedEffect(Unit) { m.refresh() }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text("שלט חכם", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            IconButton(onClick = onSettings) { Icon(Icons.Filled.Settings, contentDescription = "הגדרות") }
        }
        RemotePanel(m, onSetup)
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun SettingsScreen(onBack: () -> Unit, onNav: (String) -> Unit) {
    val ctx = LocalContext.current
    val m = rememberRemoteModel()
    LaunchedEffect(Unit) { m.refresh() }
    var confirmReset by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "חזרה") }
            Text("הגדרות", style = MaterialTheme.typography.headlineSmall)
        }
        m.state?.let { st ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Text("מזגן: " + (if (st.ac.supported) st.ac.proto else "לא הוגדר"))
                    Text("טלוויזיה: " + (st.tv.name ?: "לא הוגדרה"))
                    Text("גרסת שלט: ${st.version} · ${st.ip}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        WideButton("הגדרת מזגן מחדש", primary = false) { onNav("setup_ac") }
        WideButton("הגדרת טלוויזיה מחדש", primary = false) { onNav("setup_tv") }
        WideButton("לימוד כל שלט הטלוויזיה", primary = false) { onNav("learn_tv") }
        WideButton("הוספה למרכז הבקרה", primary = false) {
            if (Build.VERSION.SDK_INT >= 33) requestTile(ctx) else onNav("tile")
        }
        WideButton("הגדרות מתקדמות (בדפדפן)", primary = false) {
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(Device.baseUrl + "/")))
        }
        WideButton("חיבור שלט חדש / התקנה מחדש", primary = false) { confirmReset = true }
    }
    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text("להתחיל התקנה מחדש?") },
            text = { Text("האפליקציה תשכח את השלט הנוכחי ותעבור שוב את שלבי ההתקנה. ההגדרות שבשלט עצמו נשמרות.") },
            confirmButton = { TextButton(onClick = { confirmReset = false; Device.forget(); onNav("onboard") }) { Text("כן") } },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("ביטול") } },
        )
    }
}
