package ru.fepra.connect.canon

import org.json.JSONArray
import org.json.JSONObject

data class DayOut(
    val day: String,
    val sleepH: Double? = null,
    val restingHr: Int? = null,
    val hrv: Double? = null,
    val spo2Avg: Double? = null,
    val spo2Lowest: Double? = null,
    val respiration: Double? = null,
    val sleepDeepH: Double? = null,
    val sleepRemH: Double? = null,
    val steps: Long? = null,
    val vo2max: Double? = null,
    val weightKg: Double? = null,
) {
    fun isEmpty() = listOf(sleepH, restingHr, hrv, spo2Avg, spo2Lowest, respiration,
        sleepDeepH, sleepRemH, steps, vo2max, weightKg).all { it == null }
}

data class ActivityOut(
    val activityId: String,
    val sport: String,
    val startIso: String,
    val durationMin: Double?,
    val avgHr: Int? = null,
    val maxHr: Int? = null,
    val calories: Int? = null,
    val distanceKm: Double? = null,
    val elevationGainM: Double? = null,
    val paceSecPerKm: Double? = null,
    val hrSeries: List<LongArray>? = null,
)

object PayloadJson {
    fun build(days: List<DayOut>, acts: List<ActivityOut>): String {
        val o = JSONObject()
        o.put("provider", "samsung")
        val da = JSONArray()
        for (d in days) {
            if (d.isEmpty()) continue
            val j = JSONObject()
            j.put("day", d.day)
            put(j, "sleep_h", d.sleepH)
            put(j, "resting_hr", d.restingHr)
            put(j, "hrv", d.hrv)
            put(j, "spo2_avg", d.spo2Avg)
            put(j, "spo2_lowest", d.spo2Lowest)
            put(j, "respiration", d.respiration)
            put(j, "sleep_deep_h", d.sleepDeepH)
            put(j, "sleep_rem_h", d.sleepRemH)
            put(j, "steps", d.steps)
            put(j, "vo2max", d.vo2max)
            put(j, "weight_kg", d.weightKg)
            da.put(j)
        }
        o.put("days", da)
        val aa = JSONArray()
        for (a in acts) {
            val j = JSONObject()
            j.put("activity_id", a.activityId)
            j.put("sport", a.sport)
            j.put("start", a.startIso)
            put(j, "duration_min", a.durationMin)
            put(j, "avg_hr", a.avgHr)
            put(j, "max_hr", a.maxHr)
            put(j, "calories", a.calories)
            put(j, "distance_km", a.distanceKm)
            put(j, "elevation_gain_m", a.elevationGainM)
            put(j, "avg_pace_s_per_km", a.paceSecPerKm)
            a.hrSeries?.let { series ->
                val sa = JSONArray()
                for (p in series) sa.put(JSONArray().put(p[0]).put(p[1]))
                j.put("hr_series", sa)
            }
            aa.put(j)
        }
        o.put("activities", aa)
        return o.toString()
    }

    private fun put(j: JSONObject, key: String, v: Any?) {
        if (v != null) j.put(key, v)
    }
}
