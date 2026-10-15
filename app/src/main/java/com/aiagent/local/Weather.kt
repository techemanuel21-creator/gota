package com.aiagent.local

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Real weather data from MET Norway (free, no key, commercial use allowed with attribution
 * "Dados: MET Norway"). Builds a short, direct answer for the exact question asked.
 */
object Weather {

    private data class Point(val time: OffsetDateTime, val temp: Double, val symbol: String?, val rainMm: Double)

    private fun fetch(lat: Double, lon: Double): List<Point> {
        val url = String.format(
            Locale.US,
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=%.3f&lon=%.3f", lat, lon
        )
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.setRequestProperty("User-Agent", "GotaApp/1.0 (Android assistant)")
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        val body = connection.inputStream.bufferedReader().use { it.readText() }
        connection.disconnect()

        val series = JSONObject(body).getJSONObject("properties").getJSONArray("timeseries")
        return (0 until series.length()).map { i ->
            val item = series.getJSONObject(i)
            val data = item.getJSONObject("data")
            val details = data.getJSONObject("instant").getJSONObject("details")
            val next = data.optJSONObject("next_1_hours") ?: data.optJSONObject("next_6_hours")
            Point(
                time = OffsetDateTime.parse(item.getString("time")),
                temp = details.getDouble("air_temperature"),
                symbol = next?.optJSONObject("summary")?.optString("symbol_code"),
                rainMm = next?.optJSONObject("details")?.optDouble("precipitation_amount", 0.0) ?: 0.0
            )
        }
    }

    /** Blocking (network); call off the main thread. */
    fun answer(question: String, lat: Double, lon: Double, city: String?): String {
        val points = fetch(lat, lon)
        if (points.isEmpty()) return "Não consegui pegar a previsão do tempo agora."
        val q = question.lowercase(Locale("pt", "BR"))
        val where = city?.let { "em $it" } ?: "aí"
        val zone = ZoneId.systemDefault()
        val asksRain = q.contains("chuv") || q.contains("chover") || q.contains("guarda-chuva") || q.contains("guarda chuva")

        if (q.contains("amanhã") || q.contains("amanha")) {
            val tomorrow = LocalDate.now(zone).plusDays(1)
            val day = points.filter { it.time.atZoneSameInstant(zone).toLocalDate() == tomorrow }
            if (day.isEmpty()) return "Ainda não tenho a previsão de amanhã."
            val min = day.minOf { it.temp }.roundToInt()
            val max = day.maxOf { it.temp }.roundToInt()
            val rain = day.sumOf { it.rainMm }
            if (asksRain) {
                return if (rain >= 0.5) "Sim, deve chover amanhã $where (cerca de ${rain.roundToInt()} mm)."
                else "Não, a previsão é de tempo seco amanhã $where."
            }
            val sky = describe(day.mapNotNull { it.symbol }.groupingBy { it }.eachCount().maxByOrNull { it.value }?.key)
            return "Amanhã $where: mínima de $min °C e máxima de $max °C${sky?.let { ", $it" } ?: ""}."
        }

        val now = points.first()
        if (asksRain) {
            val nextHours = points.take(6)
            val firstRain = nextHours.firstOrNull { it.rainMm >= 0.2 }
            return if (firstRain == null) "Não, não tem previsão de chuva $where nas próximas horas."
            else {
                val hour = firstRain.time.atZoneSameInstant(zone).hour
                if (firstRain == now) "Sim, está chovendo ou deve chover agora $where."
                else "Sim, deve chover $where por volta das ${hour}h."
            }
        }

        val sky = describe(now.symbol)
        return "Agora $where faz ${now.temp.roundToInt()} °C${sky?.let { ", com $it" } ?: ""}."
    }

    /** One sentence for the daily briefing: current temperature, sky and rain for the rest of today. */
    fun brief(lat: Double, lon: Double, city: String?): String {
        val points = fetch(lat, lon)
        if (points.isEmpty()) return ""
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val rest = points.filter { it.time.atZoneSameInstant(zone).toLocalDate() == today }
        val now = points.first()
        val max = (rest.ifEmpty { listOf(now) }).maxOf { it.temp }.roundToInt()
        val rainAt = rest.firstOrNull { it.rainMm >= 0.2 }?.time?.atZoneSameInstant(zone)?.hour
        val sky = describe(now.symbol)
        val where = city?.let { "Em $it" } ?: "Aí"
        val rain = if (rainAt == null) "sem previsão de chuva hoje" else "com previsão de chuva por volta das ${rainAt}h"
        return "$where faz ${now.temp.roundToInt()} °C agora${sky?.let { ", $it" } ?: ""}, máxima de $max °C, $rain."
    }

    private fun describe(symbolCode: String?): String? {
        val s = symbolCode?.substringBefore('_') ?: return null
        return when {
            s.contains("thunder") -> "chuva com trovoadas"
            s.contains("heavyrain") -> "chuva forte"
            s.contains("lightrain") -> "chuva fraca"
            s.contains("rain") -> "chuva"
            s.contains("sleet") -> "chuva com granizo"
            s.contains("snow") -> "neve"
            s == "fog" -> "neblina"
            s == "partlycloudy" -> "céu parcialmente nublado"
            s == "cloudy" -> "céu nublado"
            s == "fair" -> "poucas nuvens"
            s == "clearsky" -> "céu limpo"
            else -> null
        }
    }
}
