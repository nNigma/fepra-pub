package ru.fepra.connect

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import ru.fepra.connect.canon.Mapping
import ru.fepra.connect.canon.StageIv

class MappingTest {
    @Test fun sleepFromStages() {
        val stages = listOf(
            StageIv(0, 3600, "light"),
            StageIv(3600, 7200, "deep"),
            StageIv(7200, 9000, "rem"),
            StageIv(9000, 9600, "awake"),
        )
        val s = Mapping.sleep(stages, sessionSec = 9600)
        assertEquals(2.5, s.hours, 0.01)
        assertEquals(1.0, s.deepH!!, 0.01)
        assertEquals(0.5, s.remH!!, 0.01)
    }

    @Test fun sleepWithoutStagesFallsBackToSession() {
        val s = Mapping.sleep(emptyList(), sessionSec = 7 * 3600L)
        assertEquals(7.0, s.hours, 0.01)
        assertNull(s.deepH)
        assertNull(s.remH)
    }

    @Test fun decimateCapsSeries() {
        val series = (0 until 5000).map { longArrayOf(it.toLong(), 120L + (it % 40)) }
        val out = Mapping.decimate(series, cap = 1600)
        assert(out.size <= 1600)
        assertEquals(0L, out.first()[0])
    }

    @Test fun paceNullWithoutDistance() {
        assertNull(Mapping.paceSecPerKm(1800, null))
        assertNull(Mapping.paceSecPerKm(1800, 0.0))
        assertEquals(300.0, Mapping.paceSecPerKm(1800, 6.0)!!, 0.01)
    }

    @Test fun sportMapping() {
        assertEquals("run", Mapping.sport(Mapping.T_RUNNING))
        assertEquals("run", Mapping.sport(Mapping.T_RUNNING_TREADMILL))
        assertEquals("bike", Mapping.sport(Mapping.T_BIKING))
        assertEquals("swim", Mapping.sport(Mapping.T_SWIMMING_POOL))
        assertEquals("other", Mapping.sport(999))
    }
}
