package com.aiagent.local

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import java.util.Locale
import java.util.concurrent.Executors

/**
 * Keeps a cached, human-readable approximation of where the user is (neighborhood, city, state).
 * Lookups are asynchronous so callers never block; the first call after startup may return null.
 */
object LocationHelper {

    @Volatile private var cachedCity: String? = null
    @Volatile private var cachedPlace: String? = null
    @Volatile private var cachedCoordinates: Pair<Double, Double>? = null
    @Volatile private var lastRefresh = 0L
    private val executor = Executors.newSingleThreadExecutor()

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun currentCity(context: Context): String? {
        warmUp(context)
        return cachedCity
    }

    fun currentPlace(context: Context): String? {
        warmUp(context)
        return cachedPlace
    }

    fun coordinates(context: Context): Pair<Double, Double>? {
        warmUp(context)
        return cachedCoordinates
    }

    fun warmUp(context: Context) {
        val now = System.currentTimeMillis()
        if (cachedCity != null && now - lastRefresh < 10 * 60_000) return
        if (!hasPermission(context)) return
        lastRefresh = now
        val app = context.applicationContext
        executor.execute { refresh(app) }
    }

    @SuppressLint("MissingPermission")
    private fun refresh(context: Context) {
        val lm = context.getSystemService(LocationManager::class.java) ?: return
        val lastKnown = lm.getProviders(true)
            .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
            .maxByOrNull { it.time }

        if (lastKnown != null && System.currentTimeMillis() - lastKnown.time < 30 * 60_000) {
            geocode(context, lastKnown)
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val provider = when {
                lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
                lm.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
                else -> null
            }
            if (provider != null) {
                lm.getCurrentLocation(provider, null, executor) { location ->
                    (location ?: lastKnown)?.let { geocode(context, it) }
                }
                return
            }
        }
        lastKnown?.let { geocode(context, it) }
    }

    @Suppress("DEPRECATION")
    private fun geocode(context: Context, location: Location) {
        cachedCoordinates = location.latitude to location.longitude
        val address = runCatching {
            Geocoder(context, Locale("pt", "BR")).getFromLocation(location.latitude, location.longitude, 1)?.firstOrNull()
        }.getOrNull() ?: return

        val city = address.locality ?: address.subAdminArea ?: return
        cachedCity = city
        cachedPlace = listOfNotNull(address.subLocality, city, address.adminArea).distinct().joinToString(", ")
    }
}
