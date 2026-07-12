package ru.fepra.connect

import androidx.health.connect.client.records.ExerciseSessionRecord
import org.junit.Assert.assertEquals
import org.junit.Test
import ru.fepra.connect.canon.Mapping

class SportsBridgeTest {
    @Test fun constantsMatchAndroidx() {
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_RUNNING, Mapping.T_RUNNING)
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL, Mapping.T_RUNNING_TREADMILL)
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_BIKING, Mapping.T_BIKING)
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY, Mapping.T_BIKING_STATIONARY)
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL, Mapping.T_SWIMMING_POOL)
        assertEquals(ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER, Mapping.T_SWIMMING_OPEN_WATER)
    }
}
