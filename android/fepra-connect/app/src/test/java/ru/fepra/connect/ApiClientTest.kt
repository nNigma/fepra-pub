package ru.fepra.connect

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ApiClientTest {
    @Test fun verifySendsBearerAndParsesOk() {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"ok":true}"""))
        server.start()
        val api = ApiClient(server.url("/").toString().trimEnd('/'), "TOK")
        assertTrue(api.verify())
        val req = server.takeRequest()
        assertEquals("/ingest/samsung/verify", req.path)
        assertEquals("Bearer TOK", req.getHeader("Authorization"))
        server.shutdown()
    }

    @Test fun verifyFalseOn401() {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(401))
        server.start()
        val api = ApiClient(server.url("/").toString().trimEnd('/'), "BAD")
        assertFalse(api.verify())
        server.shutdown()
    }

    @Test fun syncPostsJson() {
        val server = MockWebServer()
        server.enqueue(MockResponse().setBody("""{"days_written":1,"activities_written":0}"""))
        server.start()
        val api = ApiClient(server.url("/").toString().trimEnd('/'), "TOK")
        assertTrue(api.sync("""{"provider":"samsung","days":[],"activities":[]}"""))
        val req = server.takeRequest()
        assertEquals("/ingest/samsung", req.path)
        assertEquals("Bearer TOK", req.getHeader("Authorization"))
        assertTrue(req.body.readUtf8().contains("samsung"))
        server.shutdown()
    }
}
