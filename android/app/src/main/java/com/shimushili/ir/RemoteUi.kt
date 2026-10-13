@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)

package com.shimushili.ir

import android.content.Context
import android.os.Build
import android.widget.Toast
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val ctx = LocalContext.current
    val dark = isSystemInDarkTheme()
    val scheme = when {
        Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(ctx) else dynamicLightColorScheme(ctx)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    MaterialTheme(colorScheme = scheme) {
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) { content() }
    }
}

/** Device state for one screen, plus the actions the remote sends. */
class RemoteModel(private val scope: CoroutineScope, private val ctx: Context) {
    var state by mutableStateOf<DevState?>(null)
    var error by mutableStateOf<String?>(null)

    fun refresh() {
        scope.launch {
            try {
                state = parseState(Api.call("/api/state"))
                error = null
            } catch (e: Exception) {
                error = e.message ?: "אין חיבור למכשיר"
            }
        }
    }

    fun send(path: String, after: (JSONObject) -> Unit = {}) {
        scope.launch {
            try {
                after(Api.call(path))
            } catch (e: Exception) {
                toast(e.message)
            }
        }
    }

    fun ac(q: String) = send("/api/ac?$q") { j -> j.optJSONObject("ac")?.let { a -> state = state?.copy(ac = parseAc(a)) } }
    fun tv(key: String) = send("/api/tv?key=$key")
    fun toast(m: String?) = Toast.makeText(ctx, m ?: "שגיאה", Toast.LENGTH_SHORT).show()
}

@Composable
fun rememberRemoteModel(): RemoteModel {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    return remember { RemoteModel(scope, ctx) }
}

// ---------------------------------------------------------------- remote
/** AC and TV remotes side by side: swipe left/right (or tap the switch) to change. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun RemotePanel(m: RemoteModel, onSetup: (String) -> Unit) {
    val st = m.state
    val pager = rememberPagerState(initialPage = if (Device.lastTab == "tv") 1 else 0) { 2 }
    val scope = rememberCoroutineScope()
    LaunchedEffect(pager.currentPage) { Device.lastTab = if (pager.currentPage == 1) "tv" else "ac" }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        TabSwitch(if (pager.currentPage == 1) "tv" else "ac") { t -> scope.launch { pager.animateScrollToPage(if (t == "tv") 1 else 0) } }
        when {
            st == null && m.error != null -> ErrorBox(m.error ?: "") { m.refresh() }
            st == null -> Box(Modifier.fillMaxWidth().height(220.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            else -> HorizontalPager(state = pager, verticalAlignment = Alignment.Top, pageSpacing = 16.dp) { page ->
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    if (page == 0) AcPanel(m, st, onSetup) else TvPanel(m, st, onSetup)
                }
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            repeat(2) { i ->
                Box(
                    Modifier.padding(3.dp).size(if (pager.currentPage == i) 8.dp else 6.dp).clip(CircleShape)
                        .background(if (pager.currentPage == i) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant),
                )
            }
        }
    }
}

@Composable
fun TabSwitch(tab: String, onTab: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(50)).background(MaterialTheme.colorScheme.surfaceVariant).padding(4.dp),
    ) {
        listOf("ac" to "❄️  מזגן", "tv" to "📺  טלוויזיה").forEach { (id, label) ->
            val sel = id == tab
            Surface(
                onClick = { onTab(id) },
                shape = RoundedCornerShape(50),
                color = if (sel) MaterialTheme.colorScheme.primary else Color.Transparent,
                contentColor = if (sel) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f).height(44.dp),
            ) {
                Box(contentAlignment = Alignment.Center) { Text(label, fontWeight = FontWeight.SemiBold) }
            }
        }
    }
}

@Composable
fun ErrorBox(msg: String, onRetry: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(vertical = 30.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("📡", fontSize = 40.sp)
        Text(msg, textAlign = TextAlign.Center, modifier = Modifier.padding(8.dp))
        Button(onClick = onRetry) { Text("נסה שוב") }
    }
}

@Composable
fun SetupCard(text: String, button: String, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(12.dp))
            Button(onClick = onClick) { Text(button) }
        }
    }
}

/** A remote key with haptic feedback. */
@Composable
fun Key(
    label: String, modifier: Modifier = Modifier, dim: Boolean = false, color: Color? = null,
    height: Int = 56, fontSize: Int = 17, onClick: () -> Unit,
) {
    val haptic = LocalHapticFeedback.current
    FilledTonalButton(
        onClick = { haptic.performHapticFeedback(HapticFeedbackType.LongPress); onClick() },
        modifier = modifier.height(height.dp).alpha(if (dim) 0.45f else 1f),
        shape = RoundedCornerShape(18.dp),
        contentPadding = PaddingValues(4.dp),
        colors = if (color != null) ButtonDefaults.filledTonalButtonColors(containerColor = color, contentColor = Color.White)
        else ButtonDefaults.filledTonalButtonColors(),
    ) { Text(label, fontSize = fontSize.sp, maxLines = 1) }
}

@Composable
fun AcPanel(m: RemoteModel, st: DevState, onSetup: (String) -> Unit) {
    val ac = st.ac
    val customs = st.custom.filter { it.g == "ac" }
    if (!ac.supported && customs.isEmpty()) {
        SetupCard("המזגן עוד לא הוגדר", "הגדר מזגן") { onSetup("ac") }
        return
    }
    if (ac.supported) {
        val scope = rememberCoroutineScope()
        var temp by remember(ac.temp) { mutableIntStateOf(ac.temp) }
        var job by remember { mutableStateOf<Job?>(null) }
        fun bump(d: Int) {
            temp = (temp + d).coerceIn(16, 30)
            job?.cancel()
            job = scope.launch { delay(500); m.ac("temp=$temp&power=on") }
        }
        Key(
            if (ac.power) "⏻  דולק" else "⏻  כבוי", Modifier.fillMaxWidth(), height = 60, fontSize = 19,
            color = if (ac.power) Color(0xFF16A34A) else Color(0xFFDC2626),
        ) { m.ac("power=toggle") }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceEvenly) {
            Key("+", Modifier.size(64.dp), height = 64, fontSize = 28) { bump(1) }
            Text("$temp°", fontSize = 60.sp, fontWeight = FontWeight.Bold)
            Key("−", Modifier.size(64.dp), height = 64, fontSize = 28) { bump(-1) }
        }
        ChipRow(listOf("cool" to "❄️ קירור", "heat" to "🔥 חימום", "auto" to "🔄 אוטו", "dry" to "💧 ייבוש", "fan" to "🌀 מאוורר"), ac.mode) {
            m.ac("mode=$it&power=on")
        }
        ChipRow(listOf("auto" to "מאוורר אוטו", "low" to "נמוך", "medium" to "בינוני", "high" to "גבוה"), ac.fan) { m.ac("fan=$it") }
        ChipRow(listOf("on" to "נדנוד פועל", "off" to "נדנוד כבוי"), if (ac.swing) "on" else "off") { m.ac("swing=$it") }
    }
    CustomGrid(m, customs, "ac")
}

@Composable
fun ChipRow(items: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        items.forEach { (id, label) ->
            FilterChip(
                selected = id == selected, onClick = { onSelect(id) },
                label = { Text(label, fontSize = 13.sp, maxLines = 1) },
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
fun TvPanel(m: RemoteModel, st: DevState, onSetup: (String) -> Unit) {
    val tv = st.tv
    val customs = st.custom.filter { it.g == "tv" }
    if (tv.name == null && customs.isEmpty()) {
        SetupCard("הטלוויזיה עוד לא הוגדרה", "הגדר טלוויזיה") { onSetup("tv") }
        return
    }
    @Composable
    fun K(label: String, key: String, modifier: Modifier, color: Color? = null, fontSize: Int = 17) =
        Key(label, modifier, dim = !tv.has(key), color = color, fontSize = fontSize) { m.tv(key) }

    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        K("⏻", "power", Modifier.weight(1f), Color(0xFFDC2626), 22)
        K("⎆ מקור", "input", Modifier.weight(1f))
        K("🔇", "mute", Modifier.weight(1f), fontSize = 20)
    }
    // D-pad
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        K("▲", "up", Modifier.width(84.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            K("▶", "right", Modifier.width(84.dp))
            Key("OK", Modifier.size(84.dp), dim = !tv.has("ok"), height = 84, fontSize = 20) { m.tv("ok") }
            K("◀", "left", Modifier.width(84.dp))
        }
        K("▼", "down", Modifier.width(84.dp))
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            K("🔊 +", "vol_up", Modifier.fillMaxWidth())
            K("🔉 −", "vol_down", Modifier.fillMaxWidth())
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            K("↩ חזרה", "back", Modifier.fillMaxWidth())
            K("⌂ בית", "home", Modifier.fillMaxWidth())
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            K("ערוץ +", "ch_up", Modifier.fillMaxWidth())
            K("ערוץ −", "ch_down", Modifier.fillMaxWidth())
        }
    }
    CustomGrid(m, customs, "tv")
}

// ---------------------------------------------------------------- custom buttons
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun CustomGrid(m: RemoteModel, list: List<CustomBtn>, g: String) {
    var adding by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<CustomBtn?>(null) }
    val haptic = LocalHapticFeedback.current
    val cells: List<CustomBtn?> = list + listOf(null)  // null = "add" tile
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        cells.chunked(3).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { c ->
                    val mod = Modifier.weight(1f).height(50.dp)
                    if (c == null) {
                        OutlinedButton(onClick = { adding = true }, modifier = mod, shape = RoundedCornerShape(16.dp)) { Text("＋ כפתור") }
                    } else {
                        Surface(
                            shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.secondaryContainer,
                            modifier = mod.combinedClickable(
                                onClick = { haptic.performHapticFeedback(HapticFeedbackType.LongPress); m.send("/api/custom?id=${c.id}") },
                                onLongClick = { deleting = c },
                            ),
                        ) { Box(contentAlignment = Alignment.Center) { Text(c.name, maxLines = 1, modifier = Modifier.padding(horizontal = 6.dp)) } }
                    }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
    if (adding) AddCustomDialog(g) { adding = false; m.refresh() }
    deleting?.let { c ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("למחוק את \"${c.name}\"?") },
            confirmButton = { TextButton(onClick = { deleting = null; m.send("/api/custom/delete?id=${c.id}") { m.refresh() } }) { Text("מחק") } },
            dismissButton = { TextButton(onClick = { deleting = null }) { Text("ביטול") } },
        )
    }
}

@Composable
fun AddCustomDialog(g: String, onClose: () -> Unit) {
    var name by remember { mutableStateOf("") }
    var learning by remember { mutableStateOf(false) }
    if (learning) {
        LearnDialog("כפתור חדש", listOf(LearnItem(name, "type=custom&g=$g&name=${enc(name)}"))) { onClose() }
        return
    }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("כפתור חדש") },
        text = {
            OutlinedTextField(
                value = name, onValueChange = { name = it.take(40) }, singleLine = true,
                label = { Text(if (g == "ac") "שם (למשל: מצב שינה)" else "שם (למשל: Netflix)") },
            )
        },
        confirmButton = { TextButton(enabled = name.isNotBlank(), onClick = { learning = true }) { Text("המשך ללימוד") } },
        dismissButton = { TextButton(onClick = onClose) { Text("ביטול") } },
    )
}

// ---------------------------------------------------------------- learning
data class LearnItem(val label: String, val query: String, val hint: String = "כוון את השלט המקורי אל המכשיר ולחץ על הכפתור")

/** Learns one or more buttons in a row, with skip / retry. */
@Composable
fun LearnDialog(title: String, items: List<LearnItem>, onClose: (Int) -> Unit) {
    var i by remember { mutableIntStateOf(0) }
    var ok by remember { mutableIntStateOf(0) }
    var attempt by remember { mutableIntStateOf(0) }
    var fail by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(i, attempt) {
        if (i >= items.size) return@LaunchedEffect
        fail = null
        val r = runCatching { Api.learn(items[i].query) }.getOrElse { "error" to (it.message ?: "שגיאה") }
        if (r.first == "done") { ok++; i++ } else fail = r.second
    }
    fun close() { scope.launch { Api.cancelLearn() }; onClose(ok) }
    val done = i >= items.size
    AlertDialog(
        onDismissRequest = {},
        title = { Text(if (done) "✅ סיום" else title + if (items.size > 1) " (${i + 1}/${items.size})" else "") },
        text = {
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                if (done) {
                    Text(if (items.size == 1) "הכפתור נשמר" else "נלמדו $ok כפתורים")
                } else {
                    if (items.size > 1) LinearProgressIndicator(progress = { i.toFloat() / items.size }, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(16.dp))
                    if (fail == null) Pulse() else Text("⚠️", fontSize = 40.sp)
                    Spacer(Modifier.height(12.dp))
                    Text("לחץ בשלט המקורי על:", style = MaterialTheme.typography.bodySmall)
                    Text(items[i].label, fontSize = 26.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(8.dp))
                    Text(fail ?: items[i].hint, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            when {
                done -> TextButton(onClick = { onClose(ok) }) { Text("סיום") }
                fail != null -> TextButton(onClick = { attempt++ }) { Text("נסה שוב") }
                items.size > 1 -> TextButton(onClick = { scope.launch { Api.cancelLearn(); i++ } }) { Text("דלג") }
            }
        },
        dismissButton = { if (!done) TextButton(onClick = { close() }) { Text("ביטול") } },
    )
}

@Composable
fun Pulse() {
    val t = rememberInfiniteTransition(label = "pulse")
    val s by t.animateFloat(0.8f, 1.2f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "s")
    Box(Modifier.size(56.dp).scale(s).clip(CircleShape).background(MaterialTheme.colorScheme.primary))
}
