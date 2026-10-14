@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.shimushili.ir

import android.content.Intent
import android.net.Network
import android.provider.Settings
import android.os.Build
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/** One full-screen step of the setup flow. */
@Composable
fun StepScreen(emoji: String, title: String, body: String, content: @Composable ColumnScope.() -> Unit = {}) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(36.dp))
        Text(emoji, fontSize = 60.sp)
        Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        if (body.isNotEmpty()) Text(body, textAlign = TextAlign.Center, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(6.dp))
        content()
    }
}

@Composable
fun WideButton(text: String, primary: Boolean = true, onClick: () -> Unit) {
    val mod = Modifier.fillMaxWidth().height(52.dp)
    if (primary) Button(onClick = onClick, modifier = mod) { Text(text, fontSize = 16.sp) }
    else OutlinedButton(onClick = onClick, modifier = mod) { Text(text, fontSize = 16.sp) }
}

/** First-run setup: find/connect the device, then AC, TV and the Control Center tile. */
@Composable
fun Onboarding(onDone: () -> Unit) {
    var step by remember { mutableStateOf("welcome") }
    when (step) {
        "welcome" -> StepScreen("👋", "ברוכים הבאים", "חבר את השלט החכם לחשמל וחכה כחצי דקה עד שיעלה. ההתקנה לוקחת כמה דקות.") {
            WideButton("התחל") { step = "find" }
        }
        "find" -> FindDevice { step = "ac" }
        "ac" -> AcSetup { step = "tv" }
        "tv" -> TvSetup { step = "tile" }
        else -> TileStep(onDone)
    }
}

// ---------------------------------------------------------------- find / connect the device
// Step 1: join the device's own network (IR_WIFI) – automatically, or by hand in WiFi settings.
// Step 2: send it the home WiFi. Step 3 (AC/TV) runs after onFound().
@Composable
fun FindDevice(onFound: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val apBase = "http://192.168.4.1"
    val canAuto = Build.VERSION.SDK_INT >= 29
    var phase by remember { mutableStateOf("searching") }
    var msg by remember { mutableStateOf("") }
    var net by remember { mutableStateOf<Network?>(null) }
    var networks by remember { mutableStateOf(listOf<String>()) }
    var ssid by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var showPass by remember { mutableStateOf(false) }
    var round by remember { mutableIntStateOf(0) }

    suspend fun loadNetworks(n: Network?) {
        val arr = runCatching { JSONArray(Api.raw("/scan", apBase, n, timeoutMs = 9000)) }.getOrNull()
        if (arr == null) {
            msg = "התחברנו ל-IR_WIFI אבל השלט לא עונה. נתק אותו מהחשמל לכמה שניות ונסה שוב."
            phase = "connect"
            return
        }
        networks = List(arr.length()) { arr.getJSONObject(it) }
            .sortedByDescending { it.optInt("r", -100) }.map { it.getString("s") }.distinct()
        msg = ""
        phase = "wifi"
    }

    fun openWifiSettings() {
        phase = "manual"
        val i = if (Build.VERSION.SDK_INT >= 29) Intent(Settings.Panel.ACTION_WIFI) else Intent(Settings.ACTION_WIFI_SETTINGS)
        runCatching { ctx.startActivity(i) }
    }

    fun autoConnect() {
        phase = "auto"
        scope.launch {
            val n = ApLink.connect(ctx)
            if (n == null) {
                msg = "החיבור האוטומטי לא הצליח – אפשר להתחבר בעצמך, זה לוקח רגע."
                phase = "connect"
            } else {
                net = n
                loadNetworks(n)
            }
        }
    }

    LaunchedEffect(round) {  // maybe it's already on the home network
        phase = "searching"
        val found = Discovery.find(ctx, 5000)
        if (found != null && Discovery.pair(found)) onFound() else phase = "connect"
    }

    if (phase == "manual") {
        LaunchedEffect(Unit) {  // wait until the phone is on IR_WIFI, then continue by itself
            while (true) {
                val n = ApLink.findManual(ctx)
                if (n != null) { net = n; loadNetworks(n); break }
                delay(2000)
            }
        }
    }

    fun join() {
        phase = "joining"
        scope.launch {
            try {
                Api.raw("/save", apBase, net, form = "s=${enc(ssid)}&p=${enc(pass)}")
                var ip: String? = null
                repeat(40) {
                    if (ip == null) {
                        delay(1500)
                        val j = runCatching { JSONObject(Api.raw("/api/conn", apBase, net)) }.getOrNull()
                        when (j?.optString("s")) {
                            "ok" -> ip = j?.optString("ip")
                            "fail" -> throw ApiException(j.optString("m").ifBlank { "השלט לא הצליח להתחבר. בדוק את הסיסמה ונסה שוב." })
                        }
                    }
                }
                val addr = ip ?: throw ApiException("השלט לא הצליח להתחבר לרשת. נסה שוב.")
                runCatching { Api.raw("/api/finish", apBase, net) }
                ApLink.release(ctx)
                net = null
                phase = "returning"
                var ok = false
                repeat(15) { if (!ok) { delay(2000); ok = Discovery.pair("http://$addr") } }
                if (!ok) { val f = Discovery.find(ctx, 10_000); ok = f != null && Discovery.pair(f) }
                if (ok) onFound() else {
                    phase = "error"
                    msg = "השלט מחובר לרשת $ssid, אבל הטלפון עוד לא מוצא אותו. ודא שהטלפון חזר לרשת $ssid ולחץ נסה שוב."
                }
            } catch (e: Exception) {
                msg = e.message ?: "שגיאה"
                phase = "wifi"
            }
        }
    }

    when (phase) {
        "searching" -> StepScreen("🔎", "מחפש את השלט…", "אם השלט כבר מחובר לרשת הביתית, נמצא אותו עכשיו.") { CircularProgressIndicator() }
        "connect" -> StepScreen(
            "📶", "שלב 1 מתוך 3: התחברות לשלט",
            (if (msg.isNotEmpty()) msg + "\n\n" else "") + "השלט משדר רשת WiFi בשם IR_WIFI. נתחבר אליה כדי להעביר לו את פרטי הרשת הביתית.",
        ) {
            if (canAuto) WideButton("התחבר אוטומטית") { autoConnect() }
            WideButton("אתחבר בעצמי בהגדרות ה-WiFi", primary = !canAuto) { openWifiSettings() }
            TextButton(onClick = { msg = ""; round++ }) { Text("השלט כבר מחובר לרשת הביתית – חפש שוב") }
            Text(
                "לא רואה רשת IR_WIFI? נתק את השלט מהחשמל, חבר שוב וחכה חצי דקה.",
                style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center,
            )
        }
        "auto" -> StepScreen("📶", "מתחבר ל-IR_WIFI…", "אשר את החיבור בחלון שיופיע.") { CircularProgressIndicator() }
        "manual" -> StepScreen(
            "📶", "התחבר לרשת IR_WIFI",
            "1. ברשימת ה-WiFi בחר IR_WIFI.\n2. אם כתוב שאין אינטרנט או נפתח דף התחברות – סגור אותו ובחר להישאר מחובר.\n3. חזור לכאן. נמשיך לבד ברגע שהחיבור יזוהה.",
        ) {
            CircularProgressIndicator()
            WideButton("פתח שוב את הגדרות ה-WiFi", primary = false) { openWifiSettings() }
            TextButton(onClick = { phase = "connect" }) { Text("חזרה") }
        }
        "joining" -> StepScreen("⏳", "מחבר את השלט לרשת $ssid", "זה לוקח עד חצי דקה.") { CircularProgressIndicator() }
        "returning" -> StepScreen("🏠", "כמעט סיימנו", "הטלפון חוזר לרשת הביתית ומחפש את השלט…") { CircularProgressIndicator() }
        "error" -> StepScreen("⚠️", "משהו לא הסתדר", msg) {
            WideButton("נסה שוב") { ApLink.release(ctx); msg = ""; round++ }
        }
        else -> StepScreen("🏠", "שלב 2 מתוך 3: לאיזו רשת לחבר את השלט?", msg) {
            networks.forEach { n ->
                Surface(
                    onClick = { ssid = n },
                    shape = RoundedCornerShape(14.dp),
                    color = if (n == ssid) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(n, Modifier.padding(16.dp)) }
            }
            OutlinedTextField(ssid, { ssid = it }, label = { Text("שם הרשת") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(
                pass, { pass = it }, label = { Text("סיסמת ה-WiFi") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                visualTransformation = if (showPass) VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                trailingIcon = { TextButton(onClick = { showPass = !showPass }) { Text(if (showPass) "הסתר" else "הצג") } },
            )
            WideButton("חבר את השלט") { if (ssid.isNotBlank()) join() }
        }
    }
}

// ---------------------------------------------------------------- AC
private val AC_BRANDS = listOf(
    "KELON168" to "Electra / Tadiran (ישראל)", "ELECTRA_AC" to "Electra (שלט YKR)", "KELON" to "Kelon / Hisense",
    "AMCOR" to "Amcor", "AIRWELL" to "Airwell", "TCL112AC" to "TCL", "GREE" to "Gree", "MIDEA" to "Midea",
    "COOLIX" to "Coolix (Midea ועוד)", "SAMSUNG_AC" to "Samsung", "LG" to "LG", "HAIER_AC_YRW02" to "Haier",
    "TOSHIBA_AC" to "Toshiba", "MITSUBISHI_AC" to "Mitsubishi Electric", "MITSUBISHI_HEAVY_152" to "Mitsubishi Heavy",
    "FUJITSU_AC" to "Fujitsu", "DAIKIN" to "Daikin", "PANASONIC_AC" to "Panasonic", "SHARP_AC" to "Sharp",
    "HITACHI_AC" to "Hitachi", "WHIRLPOOL_AC" to "Whirlpool", "VESTEL_AC" to "Vestel", "CARRIER_AC64" to "Carrier", "YORK" to "York",
)

@Composable
fun AcSetup(onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var phase by remember { mutableStateOf("detect") }
    var msg by remember { mutableStateOf("") }
    var attempt by remember { mutableIntStateOf(0) }
    when (phase) {
        "detect" -> {
            LaunchedEffect(attempt) {
                val (st, m) = runCatching { Api.learn("type=ac") }.getOrElse { "error" to (it.message ?: "") }
                msg = m
                phase = if (st == "done") "test" else "fail"
            }
            StepScreen("❄️", "שלב 3 מתוך 3: הגדרת המזגן", "כוון את השלט של המזגן אל השלט החכם ולחץ על כפתור כלשהו, למשל שינוי טמפרטורה.") {
                Pulse()
                TextButton(onClick = { scope.launch { Api.cancelLearn() }; onDone() }) { Text("אין לי מזגן / דלג") }
            }
        }
        "test" -> StepScreen("✅", "המזגן זוהה", "שלחנו פקודת הפעלה (קירור 24°). המזגן נדלק?") {
            LaunchedEffect(Unit) { runCatching { Api.call("/api/ac?power=on&mode=cool&temp=24") } }
            WideButton("כן, נדלק") { onDone() }
            WideButton("לא", primary = false) { msg = "המזגן זוהה אבל לא הגיב. נסה חיפוש לפי הדגם שכתוב על השלט."; phase = "fail" }
        }
        "fail" -> StepScreen("⚠️", "לא זוהה אוטומטית", msg) {
            WideButton("נסה שוב") { attempt++; phase = "detect" }
            WideButton("חיפוש לפי דגם השלט / המזגן", primary = false) { phase = "search" }
            WideButton("בחירת מותג מרשימה", primary = false) { phase = "brands" }
            WideButton("למד מצבים קבועים מהשלט", primary = false) { phase = "scenes" }
            TextButton(onClick = onDone) { Text("דלג") }
        }
        "scenes" -> {
            StepScreen("❄️", "לימוד מצבי מזגן", "") {}
            LearnDialog("מצבי מזגן", acScenes()) { onDone() }
        }
        "search" -> AcModelSearch(onDone) { phase = "fail" }
        else -> AcBrandPicker(onDone) { phase = "fail" }
    }
}

@Composable
fun AcBrandPicker(onDone: () -> Unit, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var protos by remember { mutableStateOf<Map<String, Int>?>(null) }
    var testing by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        protos = runCatching {
            val a = JSONArray(Api.callText("/api/acprotocols"))
            List(a.length()) { a.getJSONObject(it) }.associate { it.getString("name") to it.getInt("id") }
        }.getOrElse { emptyMap() }
    }
    val p = protos
    StepScreen("❄️", "איזה מזגן יש לך?", "בחר מותג ונשלח פקודת הפעלה לבדיקה.") {
        if (p == null) CircularProgressIndicator()
        else AC_BRANDS.filter { it.first in p }.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { (proto, name) ->
                    FilledTonalButton(onClick = {
                        testing = name
                        scope.launch {
                            runCatching {
                                Api.call("/api/settings?acproto=${p[proto]}&acmodel=-1")
                                Api.call("/api/ac?power=on&mode=cool&temp=24")
                            }
                        }
                    }, modifier = Modifier.weight(1f).height(52.dp)) { Text(name, maxLines = 1, fontSize = 13.sp) }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
        TextButton(onClick = onBack) { Text("חזרה") }
    }
    testing?.let { name ->
        AlertDialog(
            onDismissRequest = { testing = null },
            title = { Text(name) },
            text = { Text("שלחנו פקודת הפעלה. המזגן נדלק?") },
            confirmButton = { TextButton(onClick = { testing = null; onDone() }) { Text("כן") } },
            dismissButton = { TextButton(onClick = { testing = null }) { Text("לא, נסה מותג אחר") } },
        )
    }
}

// ---------------------------------------------------------------- TV
val TV_KEY_LABELS = mapOf(
    "power" to "⏻ הפעלה/כיבוי", "vol_up" to "ווליום +", "vol_down" to "ווליום −", "mute" to "השתקה",
    "ch_up" to "ערוץ +", "ch_down" to "ערוץ −", "input" to "מקור / Source", "up" to "חץ למעלה ▲",
    "down" to "חץ למטה ▼", "left" to "חץ שמאלה ◀", "right" to "חץ ימינה ▶", "ok" to "OK",
    "back" to "חזרה", "home" to "בית / Home",
)

fun tvLearnAll() = TV_KEYS.map { LearnItem(TV_KEY_LABELS[it] ?: it, "type=tvkey&key=$it") }

@Composable
fun TvSetup(onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var phase by remember { mutableStateOf("detect") }
    var msg by remember { mutableStateOf("") }
    var attempt by remember { mutableIntStateOf(0) }
    when (phase) {
        "detect" -> {
            LaunchedEffect(attempt) {
                val (st, m) = runCatching { Api.learn("type=tv") }.getOrElse { "error" to (it.message ?: "") }
                msg = m
                phase = if (st == "done") "test" else "fail"
            }
            StepScreen("📺", "שלב 3 מתוך 3: הגדרת הטלוויזיה", "כוון את השלט של הטלוויזיה אל השלט החכם ולחץ על ווליום או ערוץ.") {
                Pulse()
                TextButton(onClick = { scope.launch { Api.cancelLearn() }; onDone() }) { Text("אין לי טלוויזיה / דלג") }
            }
        }
        "test" -> StepScreen("✅", "הטלוויזיה זוהתה", "$msg\nלחץ \"שלח בדיקה\" – הטלוויזיה אמורה להיכבות או להידלק.") {
            WideButton("📡 שלח בדיקה") { scope.launch { runCatching { Api.call("/api/tv?key=power") } } }
            WideButton("הטלוויזיה הגיבה ✓", primary = false) { onDone() }
            TextButton(onClick = { phase = "brands" }) { Text("לא הגיבה") }
        }
        "fail" -> StepScreen("⚠️", "לא זוהה אוטומטית", msg) {
            WideButton("נסה שוב") { attempt++; phase = "detect" }
            WideButton("בחירת מותג ובדיקה", primary = false) { phase = "brands" }
            WideButton("לימוד כל הכפתורים מהשלט", primary = false) { phase = "learn" }
            TextButton(onClick = onDone) { Text("דלג") }
        }
        "learn" -> {
            StepScreen("📺", "לימוד שלט הטלוויזיה", "") {}
            LearnDialog("לימוד שלט", tvLearnAll()) { onDone() }
        }
        else -> TvBrandTester(onDone = onDone, onLearn = { phase = "learn" })
    }
}

@Composable
fun TvBrandTester(onDone: () -> Unit, onLearn: () -> Unit) {
    val scope = rememberCoroutineScope()
    var tv by remember { mutableStateOf<TvInfo?>(null) }
    var brand by remember { mutableIntStateOf(-1) }
    var n by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) { tv = runCatching { parseState(Api.call("/api/state")).tv }.getOrNull() }
    val t = tv
    if (t == null) { StepScreen("📺", "טוען…", "") { CircularProgressIndicator() }; return }
    if (brand < 0) {
        StepScreen("📺", "איזו טלוויזיה יש לך?", "") {
            t.brands.indices.filter { b -> t.sets.any { it.first == b } }.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { b ->
                        FilledTonalButton(onClick = { brand = b; n = 0 }, modifier = Modifier.weight(1f).height(52.dp)) { Text(t.brands[b]) }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
            WideButton("המותג לא ברשימה – למד מהשלט", primary = false) { onLearn() }
        }
        return
    }
    val sets = t.sets.indices.filter { t.sets[it].first == brand }
    if (n >= sets.size) {
        StepScreen("🤔", "אף קוד לא עבד", "אין בעיה – נלמד את הכפתורים ישירות מהשלט שלך.") {
            WideButton("לימוד מהשלט") { onLearn() }
            TextButton(onClick = { brand = -1 }) { Text("בחר מותג אחר") }
        }
        return
    }
    val si = sets[n]
    StepScreen("📺", "${t.brands[brand]} – בדיקה ${n + 1} מתוך ${sets.size}", "כוון את השלט החכם לטלוויזיה ולחץ \"שלח\". הטלוויזיה אמורה להיכבות או להידלק.") {
        WideButton("📡 שלח בדיקה") { scope.launch { runCatching { Api.call("/api/tv/test?set=$si") } } }
        WideButton("✅ הטלוויזיה הגיבה", primary = false) {
            scope.launch { runCatching { Api.call("/api/settings?tvset=$si") }; onDone() }
        }
        TextButton(onClick = { n++ }) { Text("❌ לא הגיבה – נסה קוד הבא") }
    }
}

// ---------------------------------------------------------------- Control Center tile
@Composable
fun TileStep(onDone: () -> Unit) {
    val ctx = LocalContext.current
    StepScreen(
        "🎛️", "שלט במרכז הבקרה",
        "הוסף את האריח \"שלט\" למרכז הבקרה. נגיעה בו תפתח את השלט מכל מקום בטלפון.",
    ) {
        if (Build.VERSION.SDK_INT >= 33) WideButton("הוסף למרכז הבקרה") { requestTile(ctx) }
        else Text(
            "משוך למטה את מרכז הבקרה ← לחץ על העיפרון (עריכה) ← גרור את האריח \"שלט\" לרשימה.",
            textAlign = TextAlign.Center,
        )
        WideButton("סיום", primary = false) { onDone() }
    }
}
