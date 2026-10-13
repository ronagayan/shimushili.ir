@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.shimushili.ir

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val FW_RELEASE = "https://github.com/ronagayan/shimushili.ir/releases/download/firmware-latest/"

/** After the device reboots (pins / firmware), wait and find it again. */
suspend fun waitForDevice(): Boolean {
    delay(6000)
    repeat(10) {
        if (runCatching { Api.call("/api/state") }.isSuccess) return true
        delay(2000)
    }
    return false
}

// ---------------------------------------------------------------- hardware (pins)
@Composable
fun HardwareWizard(onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var phase by remember { mutableStateOf("menu") }
    var msg by remember { mutableStateOf("") }
    var found by remember { mutableIntStateOf(-1) }
    var which by remember { mutableStateOf("rx") }

    fun savePin(kind: String, pin: Int) {
        phase = "saving"
        scope.launch {
            runCatching { Api.call("/api/admin/pins?$kind=$pin") }
            val ok = waitForDevice()
            msg = if (ok) "נשמר. השלט פועל עם הפין החדש." else "נשמר, אבל השלט עוד לא חזר לרשת. חכה רגע ונסה שוב."
            phase = "done"
        }
    }

    when (phase) {
        "menu" -> StepScreen("🔧", "בדיקת חומרה", "מוצאים אוטומטית את פיני הקליטה והשידור של הלוח. עושים את זה פעם אחת.") {
            WideButton("1. מצא את מקלט ה-IR") { phase = "rx" }
            WideButton("2. מצא את נורת השידור", primary = false) { phase = "tx" }
            TextButton(onClick = onDone) { Text("חזרה") }
        }
        "rx" -> StepScreen("📡", "מציאת המקלט", "לחץ על \"התחל\" ומיד לחץ לחיצה ארוכה על כפתור בשלט כלשהו, מכוון לשלט החכם, במשך 6 שניות.") {
            WideButton("התחל") {
                phase = "scanning"
                scope.launch {
                    val j = runCatching { Api.slow("/api/admin/test/rx", 15000) }.getOrNull()
                    val pins = j?.optJSONArray("pins")
                    var best = -1
                    var bestN = 0
                    if (pins != null) for (i in 0 until pins.length()) {
                        val o = pins.getJSONObject(i)
                        if (o.getInt("n") > bestN) { bestN = o.getInt("n"); best = o.getInt("pin") }
                    }
                    found = best
                    which = "rx"
                    msg = if (best >= 0) "המקלט נמצא בפין GPIO$best." else "לא זוהתה קליטה. ודא שלחצת על השלט כל הזמן ושהוא מכוון ללוח."
                    phase = "result"
                }
            }
            TextButton(onClick = { phase = "menu" }) { Text("חזרה") }
        }
        "scanning" -> StepScreen("📡", "סורק…", "המשך ללחוץ על הכפתור בשלט") { CircularProgressIndicator() }
        "tx" -> StepScreen("💡", "מציאת נורת השידור", "שים את כף היד כ-5 ס\"מ מול השלט החכם (כדי שהאור יחזור למקלט) ולחץ \"התחל\". צריך שהמקלט כבר נמצא.") {
            WideButton("התחל") {
                phase = "scanning_tx"
                scope.launch {
                    val j = runCatching { Api.slow("/api/admin/test/txauto", 30000) }.getOrNull()
                    found = j?.optInt("pin", -1) ?: -1
                    which = "tx"
                    msg = if (found >= 0) "נורת השידור נמצאה בפין GPIO$found." else "לא נמצאה. נסה שוב עם היד קרוב יותר, או מצא קודם את המקלט."
                    phase = "result"
                }
            }
            TextButton(onClick = { phase = "menu" }) { Text("חזרה") }
        }
        "scanning_tx" -> StepScreen("💡", "בודק פינים…", "השאר את היד מול השלט החכם") { CircularProgressIndicator() }
        "result" -> StepScreen(if (found >= 0) "✅" else "⚠️", if (found >= 0) "נמצא" else "לא נמצא", msg) {
            if (found >= 0) WideButton("שמור") { savePin(which, found) }
            WideButton("נסה שוב", primary = found < 0) { phase = which }
            TextButton(onClick = { phase = "menu" }) { Text("חזרה") }
        }
        "saving" -> StepScreen("⏳", "שומר ומפעיל מחדש…", "") { CircularProgressIndicator() }
        else -> StepScreen("✅", "סיום", msg) {
            WideButton("המשך") { phase = "menu" }
            TextButton(onClick = onDone) { Text("סגור") }
        }
    }
}

// ---------------------------------------------------------------- firmware update
fun newerSemver(a: String, b: String): Boolean {  // a > b ?
    val x = a.split('.').map { it.toIntOrNull() ?: 0 }
    val y = b.split('.').map { it.toIntOrNull() ?: 0 }
    for (i in 0 until maxOf(x.size, y.size)) {
        val d = x.getOrElse(i) { 0 } - y.getOrElse(i) { 0 }
        if (d != 0) return d > 0
    }
    return false
}

suspend fun latestFirmware(): String? = withContext(Dispatchers.IO) {
    runCatching {
        val c = URL(FW_RELEASE + "version.json").openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 8000
        c.inputStream.bufferedReader().use { JSONObject(it.readText()).getString("version") }
    }.getOrNull()
}

suspend fun uploadFirmware(chip: String): String = withContext(Dispatchers.IO) {
    val bin = URL(FW_RELEASE + "firmware-$chip.bin").openStream().use { it.readBytes() }
    if (bin.size < 100_000 || bin[0] != 0xE9.toByte()) throw ApiException("קובץ הקושחה שהורד לא תקין")
    val boundary = "----irblaster" + System.currentTimeMillis()
    val head = "--$boundary\r\nContent-Disposition: form-data; name=\"update\"; filename=\"firmware.bin\"\r\nContent-Type: application/octet-stream\r\n\r\n".toByteArray()
    val tail = "\r\n--$boundary--\r\n".toByteArray()
    val c = URL(Device.baseUrl + "/update").openConnection() as HttpURLConnection
    c.requestMethod = "POST"
    c.doOutput = true
    c.connectTimeout = 10_000
    c.readTimeout = 90_000
    c.setRequestProperty("X-Key", Device.key)
    c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
    c.setFixedLengthStreamingMode(head.size + bin.size + tail.size)
    c.outputStream.use { it.write(head); it.write(bin); it.write(tail) }
    val code = c.responseCode
    val body = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
    c.disconnect()
    if (code == 401) throw ApiException("לשלט מוגדרת סיסמת ניהול – עדכן מדף המכשיר")
    if (code !in 200..299) throw ApiException(body.ifEmpty { "העדכון נכשל ($code)" })
    body
}

@Composable
fun FirmwareUpdate(current: String, chip: String, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var latest by remember { mutableStateOf<String?>(null) }
    var phase by remember { mutableStateOf("check") }
    var msg by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        latest = latestFirmware()
        phase = when {
            latest == null -> "offline"
            newerSemver(latest!!, current) -> "available"
            else -> "uptodate"
        }
    }
    when (phase) {
        "check" -> StepScreen("🔄", "בודק עדכונים…", "") { CircularProgressIndicator() }
        "offline" -> StepScreen("⚠️", "אין חיבור לשרת העדכונים", "ודא שיש אינטרנט ונסה שוב.") { WideButton("חזרה") { onDone() } }
        "uptodate" -> StepScreen("✅", "הקושחה מעודכנת", "גרסה $current") { WideButton("חזרה") { onDone() } }
        "available" -> StepScreen("⬆️", "עדכון קושחה זמין", "גרסה ${latest} (מותקנת: $current). השלט יופעל מחדש לכמה שניות.") {
            WideButton("עדכן עכשיו") {
                phase = "updating"
                scope.launch {
                    try {
                        uploadFirmware(chip)
                        phase = "rebooting"
                        msg = if (waitForDevice()) "השלט עודכן לגרסה $latest" else "העדכון נשלח. השלט עוד מופעל מחדש – חכה רגע."
                        phase = "done"
                    } catch (e: Exception) {
                        msg = e.message ?: "העדכון נכשל"
                        phase = "failed"
                    }
                }
            }
            TextButton(onClick = onDone) { Text("לא עכשיו") }
        }
        "updating" -> StepScreen("⏳", "מעדכן…", "אל תנתק את השלט מהחשמל. זה לוקח עד דקה.") { CircularProgressIndicator() }
        "rebooting" -> StepScreen("⏳", "השלט מופעל מחדש…", "") { CircularProgressIndicator() }
        "failed" -> StepScreen("⚠️", "העדכון נכשל", msg + "\nהשלט ממשיך לעבוד עם הגרסה הקודמת.") {
            WideButton("נסה שוב") { phase = "available" }
            TextButton(onClick = onDone) { Text("חזרה") }
        }
        else -> StepScreen("✅", "סיום", msg) { WideButton("חזרה") { onDone() } }
    }
}
