package ru.fepra.connect

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import ru.fepra.connect.canon.ActivityOut
import ru.fepra.connect.canon.DayOut
import ru.fepra.connect.canon.PayloadJson

class PayloadJsonTest {
    @Test fun buildsServerKeys() {
        val day = DayOut(
            day = "2026-07-09", sleepH = 7.2, restingHr = 52, hrv = 41.0,
            spo2Avg = 96.0, spo2Lowest = 91.0, respiration = 14.0,
            sleepDeepH = 1.1, sleepRemH = 1.4, steps = 8200, vo2max = 48.0, weightKg = null,
        )
        val act = ActivityOut(
            activityId = "hc-abc", sport = "run", startIso = "2026-07-09T07:12:00+03:00",
            durationMin = 42.0, avgHr = 150, maxHr = 175, calories = 430,
            distanceKm = 7.1, elevationGainM = 35.0, paceSecPerKm = 355.0,
            hrSeries = listOf(longArrayOf(0, 120), longArrayOf(5, 132)),
        )
        val o = JSONObject(PayloadJson.build(listOf(day), listOf(act)))
        assertEquals("samsung", o.getString("provider"))
        val d = o.getJSONArray("days").getJSONObject(0)
        assertEquals(7.2, d.getDouble("sleep_h"), 0.001)
        assertEquals(1.1, d.getDouble("sleep_deep_h"), 0.001)
        assertEquals(14.0, d.getDouble("respiration"), 0.001)
        assertFalse(d.has("weight_kg"))
        val a = o.getJSONArray("activities").getJSONObject(0)
        assertEquals("hc-abc", a.getString("activity_id"))
        assertEquals("2026-07-09T07:12:00+03:00", a.getString("start"))
        assertEquals(355.0, a.getDouble("avg_pace_s_per_km"), 0.001)
        assertEquals(120, a.getJSONArray("hr_series").getJSONArray(0).getInt(1))
    }

    @Test fun skipsEmptyDay() {
        val empty = DayOut(day = "2026-07-09")
        val o = JSONObject(PayloadJson.build(listOf(empty), emptyList()))
        assertEquals(0, o.getJSONArray("days").length())
    }
}
