// UNTESTED: written without an Android SDK or devices. Needs >=2 physical Android devices to verify (see docs/OFFLINE_NETWORKING.md).
// Transport only: JS owns validation, signatures, dedup and expiry. This module just ferries newline-delimited frames:
//   HELLO {"v":1,"peer":"<peerId>","known":["<id>",...]}   then   MSG <envelope-json> ...   then   BYE
// Discovery: Wi-Fi Direct DNS-SD ("_floodres._tcp") and, when on the same Wi-Fi LAN, NsdManager (mDNS). TCP port 8988.
package com.floodresilience.p2p

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WpsInfo
import android.net.wifi.p2p.WifiP2pConfig
import android.net.wifi.p2p.WifiP2pDevice
import android.net.wifi.p2p.WifiP2pManager
import android.net.wifi.p2p.nsd.WifiP2pDnsSdServiceInfo
import android.net.wifi.p2p.nsd.WifiP2pDnsSdServiceRequest
import android.os.Build
import android.os.Looper
import android.util.Log
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.modules.core.DeviceEventManagerModule
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

@SuppressLint("MissingPermission")
class FloodP2pModule(private val ctx: ReactApplicationContext) : ReactContextBaseJavaModule(ctx) {
    override fun getName() = "FloodP2p"

    companion object {
        const val TAG = "FloodP2p"            // adb logcat -s FloodP2p:I
        const val PORT = 8988
        const val SERVICE_TYPE = "_floodres._tcp"
        const val MAX_LINE = 16 * 1024      // hostile-peer limits: bounded line size, message count and time
        const val MAX_MSGS = 100
        const val IO_TIMEOUT_MS = 10_000
        const val CONTACT_COOLDOWN_MS = 30_000L
    }

    private val pool = Executors.newCachedThreadPool()
    private val scheduler = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var send = JSONArray()           // envelopes ready for the wire (hop_count already incremented by JS)
    @Volatile private var known = JSONArray()          // every message id we already hold
    @Volatile private var running = false
    private var peerId = ""
    private var server: ServerSocket? = null
    private val lastContact = ConcurrentHashMap<String, Long>()
    private val seenPeers = ConcurrentHashMap<String, Long>()

    // Wi-Fi Direct
    private var p2pMgr: WifiP2pManager? = null
    private var p2pCh: WifiP2pManager.Channel? = null
    private var receiver: BroadcastReceiver? = null
    // LAN mDNS
    private var nsd: NsdManager? = null
    private var regListener: NsdManager.RegistrationListener? = null
    private var discListener: NsdManager.DiscoveryListener? = null
    @Volatile private var resolving = false

    @ReactMethod fun addListener(eventName: String) {}
    @ReactMethod fun removeListeners(count: Int) {}

    @ReactMethod
    fun setOutbox(json: String) {
        try {
            val o = JSONObject(json)
            send = o.getJSONArray("send"); known = o.getJSONArray("known")
        } catch (e: Exception) { send = JSONArray(); known = JSONArray() }
    }

    @ReactMethod
    fun start(id: String, promise: Promise) {
        if (running) { promise.resolve(null); return }
        peerId = id; running = true
        Log.i(TAG, "start peer=${id.take(8)} port=$PORT")
        try {
            startServer(); startNsd(); startWifiDirect()
            scheduler.scheduleWithFixedDelay({ rediscover(); emitPeers() }, 30, 60, TimeUnit.SECONDS)
            promise.resolve(null)
        } catch (e: Exception) { running = false; promise.reject("P2P_START", e) }
    }

    @ReactMethod
    fun stop(promise: Promise) {
        running = false
        try { server?.close() } catch (_: Exception) {}
        try { discListener?.let { nsd?.stopServiceDiscovery(it) }; regListener?.let { nsd?.unregisterService(it) } } catch (_: Exception) {}
        try { receiver?.let { ctx.unregisterReceiver(it) } } catch (_: Exception) {}
        try { p2pMgr?.clearLocalServices(p2pCh, null); p2pMgr?.clearServiceRequests(p2pCh, null); p2pMgr?.removeGroup(p2pCh, null) } catch (_: Exception) {}
        receiver = null
        promise.resolve(null)
    }

    // ---------------------------------------------------------------- transport
    private fun startServer() {
        val ss = ServerSocket(); ss.reuseAddress = true; ss.bind(InetSocketAddress(PORT)); server = ss
        pool.submit {
            while (running) {
                try { val s = ss.accept(); Log.i(TAG, "inbound from ${s.inetAddress?.hostAddress}"); pool.submit { exchange(s) } } catch (_: Exception) { if (!running) break }
            }
        }
    }

    private fun connectAndExchange(host: String) {
        val now = System.currentTimeMillis()
        if (now - (lastContact[host] ?: 0L) < CONTACT_COOLDOWN_MS) return
        lastContact[host] = now
        Log.i(TAG, "outbound to $host")
        pool.submit {
            try { val s = Socket(); s.connect(InetSocketAddress(host, PORT), 5000); exchange(s) } catch (_: Exception) {}
        }
    }

    private fun readLine(r: BufferedReader): String? {
        val sb = StringBuilder()
        while (true) {
            val c = r.read(); if (c < 0) return if (sb.isEmpty()) null else sb.toString()
            if (c == '\n'.code) return sb.toString()
            sb.append(c.toChar()); if (sb.length > MAX_LINE) throw IllegalStateException("line too long")
        }
    }

    private fun exchange(sock: Socket) {
        try {
            sock.use { s ->
                s.soTimeout = IO_TIMEOUT_MS
                val out = BufferedWriter(OutputStreamWriter(s.getOutputStream(), Charsets.UTF_8))
                val inp = BufferedReader(InputStreamReader(s.getInputStream(), Charsets.UTF_8))
                val hello = JSONObject().put("v", 1).put("peer", peerId).put("known", known)
                out.write("HELLO $hello\n"); out.flush()
                val first = readLine(inp) ?: return
                if (!first.startsWith("HELLO ")) return
                val remote = JSONObject(first.substring(6))
                if (remote.optInt("v") != 1) return
                remote.optString("peer").takeIf { it.length == 64 }?.let { seenPeers[it] = System.currentTimeMillis(); emitPeers() }
                val remoteKnown = HashSet<String>().also { set -> remote.optJSONArray("known")?.let { a -> for (i in 0 until minOf(a.length(), 5000)) set.add(a.optString(i)) } }
                Log.i(TAG, "hello from ${remote.optString("peer").take(8)} knows=${remoteKnown.size} we_offer=${send.length()}")
                val sentIds = JSONArray()
                val writer = pool.submit {
                    try {
                        val snap = send
                        for (i in 0 until snap.length()) {
                            val e = snap.getJSONObject(i)
                            if (e.getString("message_id") in remoteKnown || sentIds.length() >= MAX_MSGS) continue
                            out.write("MSG $e\n"); sentIds.put(e.getString("message_id"))
                        }
                        out.write("BYE\n"); out.flush()
                    } catch (_: Exception) {}
                }
                var n = 0
                while (n < MAX_MSGS) {
                    val line = readLine(inp) ?: break
                    if (line == "BYE") break
                    if (line.startsWith("MSG ")) { n++; emit("p2pMessage", Arguments.createMap().apply { putString("json", line.substring(4)); putString("from", remote.optString("peer")) }) }
                }
                try { writer.get(IO_TIMEOUT_MS.toLong(), TimeUnit.MILLISECONDS) } catch (_: Exception) {}
                Log.i(TAG, "exchange done sent=${sentIds.length()} received=$n")
                if (sentIds.length() > 0) emit("p2pSent", Arguments.createMap().apply {
                    putArray("ids", Arguments.createArray().also { arr -> for (i in 0 until sentIds.length()) arr.pushString(sentIds.getString(i)) }) })
            }
        } catch (e: Exception) { Log.w(TAG, "exchange failed: ${e.javaClass.simpleName}") /* a misbehaving or vanished peer must never crash the app */ }
    }

    private fun emit(event: String, map: com.facebook.react.bridge.WritableMap) {
        if (ctx.hasActiveReactInstance()) ctx.getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java).emit(event, map)
    }
    private fun emitPeers() {
        val cutoff = System.currentTimeMillis() - 120_000
        seenPeers.entries.removeIf { it.value < cutoff }
        emit("p2pPeers", Arguments.createMap().apply { putInt("count", seenPeers.size) })
    }

    // ---------------------------------------------------------------- LAN (mDNS) discovery
    private fun startNsd() {
        val mgr = ctx.getSystemService(Context.NSD_SERVICE) as NsdManager; nsd = mgr
        val myName = "fr-" + peerId.take(8)
        val info = NsdServiceInfo().apply { serviceName = myName; serviceType = "$SERVICE_TYPE."; port = PORT }
        regListener = object : NsdManager.RegistrationListener {
            override fun onRegistrationFailed(i: NsdServiceInfo, e: Int) {}
            override fun onUnregistrationFailed(i: NsdServiceInfo, e: Int) {}
            override fun onServiceRegistered(i: NsdServiceInfo) {}
            override fun onServiceUnregistered(i: NsdServiceInfo) {}
        }
        mgr.registerService(info, NsdManager.PROTOCOL_DNS_SD, regListener)
        discListener = object : NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(t: String, e: Int) {}
            override fun onStopDiscoveryFailed(t: String, e: Int) {}
            override fun onDiscoveryStarted(t: String) {}
            override fun onDiscoveryStopped(t: String) {}
            override fun onServiceLost(i: NsdServiceInfo) {}
            override fun onServiceFound(i: NsdServiceInfo) {
                if (i.serviceName == myName || !i.serviceName.startsWith("fr-") || resolving) return
                resolving = true
                @Suppress("DEPRECATION")
                mgr.resolveService(i, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(s: NsdServiceInfo, e: Int) { resolving = false }
                    override fun onServiceResolved(s: NsdServiceInfo) { resolving = false; s.host?.hostAddress?.let { connectAndExchange(it) } }
                })
            }
        }
        mgr.discoverServices("$SERVICE_TYPE.", NsdManager.PROTOCOL_DNS_SD, discListener)
    }

    // ---------------------------------------------------------------- Wi-Fi Direct (no existing network needed)
    private fun startWifiDirect() {
        val mgr = ctx.getSystemService(Context.WIFI_P2P_SERVICE) as? WifiP2pManager ?: return
        val ch = mgr.initialize(ctx, Looper.getMainLooper(), null); p2pMgr = mgr; p2pCh = ch
        val myName = "fr-" + peerId.take(8)
        mgr.addLocalService(ch, WifiP2pDnsSdServiceInfo.newInstance(myName, SERVICE_TYPE, mapOf("v" to "1")), null)
        mgr.setDnsSdResponseListeners(ch, { instance, _, device -> if (instance.startsWith("fr-") && instance != myName) { Log.i(TAG, "wifi-direct found $instance"); connectDirect(device) } }, null)
        receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                mgr.requestConnectionInfo(ch) { info ->
                    if (!info.groupFormed) return@requestConnectionInfo
                    Log.i(TAG, "wifi-direct group formed owner=${info.isGroupOwner}")
                    if (info.isGroupOwner) scheduler.schedule({ mgr.removeGroup(ch, null) }, 20, TimeUnit.SECONDS)   // peer connects to our server
                    else info.groupOwnerAddress?.hostAddress?.let { host ->
                        pool.submit { try { val s = Socket(); s.connect(InetSocketAddress(host, PORT), 5000); exchange(s) } catch (_: Exception) {}
                            mgr.removeGroup(ch, null) }                                                      // free the radio for the next peer
                    }
                }
            }
        }
        val f = IntentFilter(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION)
        if (Build.VERSION.SDK_INT >= 33) ctx.registerReceiver(receiver, f, Context.RECEIVER_NOT_EXPORTED) else ctx.registerReceiver(receiver, f)
        rediscover()
    }

    private fun rediscover() {
        val mgr = p2pMgr ?: return; val ch = p2pCh ?: return
        mgr.clearServiceRequests(ch, null)
        mgr.addServiceRequest(ch, WifiP2pDnsSdServiceRequest.newInstance(), object : WifiP2pManager.ActionListener {
            override fun onSuccess() { mgr.discoverServices(ch, null) }
            override fun onFailure(reason: Int) {}
        })
    }

    private fun connectDirect(device: WifiP2pDevice) {
        val now = System.currentTimeMillis()
        if (now - (lastContact[device.deviceAddress] ?: 0L) < 60_000L) return
        lastContact[device.deviceAddress] = now
        val cfg = WifiP2pConfig().apply { deviceAddress = device.deviceAddress; wps.setup = WpsInfo.PBC }
        p2pMgr?.connect(p2pCh, cfg, null)   // some devices show a system consent prompt: expected platform behaviour
    }
}
