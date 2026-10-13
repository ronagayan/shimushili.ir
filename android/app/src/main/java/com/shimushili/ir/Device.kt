package com.shimushili.ir

import android.content.Context
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.os.PatternMatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.resume

/** Saved connection to the IR device (address + per-device key). */
object Device {
    private lateinit var prefs: SharedPreferences
    lateinit var app: Context
        private set

    fun init(ctx: Context) {
        if (::prefs.isInitialized) return
        app = ctx.applicationContext
        prefs = app.getSharedPreferences("device", Context.MODE_PRIVATE)
    }

    var baseUrl: String
        get() = prefs.getString("base", "") ?: ""
        set(v) = prefs.edit().putString("base", v).apply()
    var key: String
        get() = prefs.getString("key", "") ?: ""
        set(v) = prefs.edit().putString("key", v).apply()
    var lastTab: String
        get() = prefs.getString("tab", "ac") ?: "ac"
        set(v) = prefs.edit().putString("tab", v).apply()
    val configured: Boolean get() = baseUrl.isNotEmpty() && key.isNotEmpty()

    fun forget() = prefs.edit().remove("base").remove("key").apply()
}

class ApiException(msg: String) : Exception(msg)

fun enc(s: String): String = URLEncoder.encode(s, "UTF-8")

object Api {
    private suspend fun request(
        path: String, base: String, network: Network?, form: String? = null, timeoutMs: Int = 5000,
    ): String = withContext(Dispatchers.IO) {
        val url = URL(base + path)
        val conn = (network?.openConnection(url) ?: url.openConnection()) as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        if (Device.key.isNotEmpty()) conn.setRequestProperty("X-Key", Device.key)
        try {
            if (form != null) {
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                conn.outputStream.use { it.write(form.toByteArray()) }
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) {
                val msg = runCatching { JSONObject(body).optString("error") }.getOrNull()
                throw ApiException(if (!msg.isNullOrEmpty()) msg else "שגיאה מהמכשיר ($code)")
            }
            body
        } finally {
            conn.disconnect()
        }
    }

    /** Call the saved device. If it moved to a new IP, find it again on the network and retry. */
    suspend fun callText(path: String): String {
        try {
            return request(path, Device.baseUrl, null)
        } catch (e: IOException) {
            val found = Discovery.find(Device.app) ?: throw ApiException("השלט לא נמצא ברשת. ודא שהוא מחובר לחשמל ושהטלפון ברשת הביתית.")
            Device.baseUrl = found
            return request(path, found, null)
        }
    }

    suspend fun call(path: String): JSONObject = JSONObject(callText(path))

    suspend fun raw(path: String, base: String, network: Network? = null, form: String? = null): String =
        request(path, base, network, form)

    /** Start learning and wait until the device reports a result. */
    suspend fun learn(query: String): Pair<String, String> {
        call("/api/learn?$query")
        repeat(40) {
            delay(600)
            val s = call("/api/learn/status")
            val st = s.optString("status")
            if (st != "listening") return st to s.optString("msg")
        }
        return "timeout" to "לא נקלט אות"
    }

    suspend fun cancelLearn() { runCatching { call("/api/learn/cancel") } }
}

/** Finds the device on the home network via mDNS (_irblaster._tcp) – no IP needed. */
object Discovery {
    suspend fun find(ctx: Context, timeoutMs: Long = 7000): String? = withTimeoutOrNull(timeoutMs) {
        suspendCancellableCoroutine { cont ->
            val nsd = ctx.getSystemService(NsdManager::class.java)
            val done = AtomicBoolean(false)
            lateinit var listener: NsdManager.DiscoveryListener
            fun finish(v: String?) {
                if (done.compareAndSet(false, true)) {
                    runCatching { nsd.stopServiceDiscovery(listener) }
                    if (cont.isActive) cont.resume(v)
                }
            }
            listener = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(serviceType: String) {}
                override fun onDiscoveryStopped(serviceType: String) {}
                override fun onServiceLost(serviceInfo: NsdServiceInfo) {}
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) = finish(null)
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
                override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                    @Suppress("DEPRECATION")
                    nsd.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(si: NsdServiceInfo, errorCode: Int) {}
                        override fun onServiceResolved(si: NsdServiceInfo) {
                            @Suppress("DEPRECATION")
                            val host = si.host?.hostAddress ?: return
                            if (host.contains(':')) return  // IPv4 only
                            finish("http://$host")
                        }
                    })
                }
            }
            nsd.discoverServices("_irblaster._tcp", NsdManager.PROTOCOL_DNS_SD, listener)
            cont.invokeOnCancellation { runCatching { nsd.stopServiceDiscovery(listener) } }
        }
    }

    /** Get the per-device key from a device we just found. */
    suspend fun pair(base: String): Boolean {
        val k = runCatching { JSONObject(Api.raw("/api/session", base)).optString("k") }.getOrNull()
        if (k.isNullOrEmpty()) return false
        Device.baseUrl = base
        Device.key = k
        return true
    }
}

/** Temporary link to the device's own setup network (IR_WIFI…) during first setup. */
object ApLink {
    private var callback: ConnectivityManager.NetworkCallback? = null

    suspend fun connect(ctx: Context): Network? {
        if (Build.VERSION.SDK_INT < 29) return null
        val cm = ctx.getSystemService(ConnectivityManager::class.java)
        release(ctx)
        return withTimeoutOrNull(70_000) {
            suspendCancellableCoroutine { cont ->
                val spec = WifiNetworkSpecifier.Builder()
                    .setSsidPattern(PatternMatcher("IR_WIFI", PatternMatcher.PATTERN_PREFIX))
                    .build()
                val req = NetworkRequest.Builder()
                    .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                    .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .setNetworkSpecifier(spec)
                    .build()
                val cb = object : ConnectivityManager.NetworkCallback() {
                    override fun onAvailable(network: Network) { if (cont.isActive) cont.resume(network) }
                    override fun onUnavailable() { if (cont.isActive) cont.resume(null) }
                }
                callback = cb
                cm.requestNetwork(req, cb, 60_000)
            }
        }
    }

    fun release(ctx: Context) {
        val cb = callback ?: return
        callback = null
        runCatching { ctx.getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(cb) }
    }
}

// ---------------------------------------------------------------- state model
data class AcState(
    val supported: Boolean, val proto: String, val power: Boolean, val mode: String,
    val temp: Int, val fan: String, val swing: Boolean,
)

data class CustomBtn(val id: Int, val g: String, val name: String)

data class TvInfo(val set: Int, val brands: List<String>, val sets: List<Pair<Int, Int>>, val learned: List<String>) {
    fun setName(i: Int): String? {
        if (i < 0 || i >= sets.size) return null
        val brand = sets[i].first
        val same = sets.indices.filter { sets[it].first == brand }
        return brands.getOrElse(brand) { "?" } + if (same.size > 1) " (קוד ${same.indexOf(i) + 1})" else ""
    }
    val name: String? get() = setName(set) ?: if (learned.isNotEmpty()) "שלט שנלמד" else null
    fun has(key: String): Boolean {
        if (key in learned) return true
        if (set < 0 || set >= sets.size) return false
        val idx = TV_KEYS.indexOf(key)
        return idx >= 0 && ((sets[set].second shr idx) and 1) == 1
    }
}

data class DevState(val version: String, val ip: String, val ac: AcState, val tv: TvInfo, val custom: List<CustomBtn>)

val TV_KEYS = listOf("power", "vol_up", "vol_down", "mute", "ch_up", "ch_down", "input", "up", "down", "left", "right", "ok", "back", "home")

fun parseAc(a: JSONObject) = AcState(
    supported = a.optBoolean("supported"), proto = a.optString("proto"), power = a.optBoolean("power"),
    mode = a.optString("mode", "cool"), temp = a.optDouble("temp", 24.0).toInt(), fan = a.optString("fan", "auto"),
    swing = a.optBoolean("swing"),
)

fun parseState(j: JSONObject): DevState {
    val tv = j.getJSONObject("tv")
    val brands = tv.getJSONArray("brands").let { arr -> List(arr.length()) { arr.getString(it) } }
    val sets = tv.getJSONArray("sets").let { arr -> List(arr.length()) { arr.getJSONArray(it).let { p -> p.getInt(0) to p.getInt(1) } } }
    val learned = tv.getJSONArray("learned").let { arr -> List(arr.length()) { arr.getString(it) } }
    val custom = j.getJSONArray("custom").let { arr ->
        List(arr.length()) { arr.getJSONObject(it).let { c -> CustomBtn(c.getInt("id"), c.optString("g", "tv"), c.getString("name")) } }
    }
    return DevState(j.optString("v"), j.optString("ip"), parseAc(j.getJSONObject("ac")), TvInfo(tv.optInt("set", -1), brands, sets, learned), custom)
}
