"""Real owned-loopback transport regression; no market/provider imports."""
import asyncio
import socket

import pytest
import uvicorn


@pytest.mark.asyncio
async def test_keepalive_timer_does_not_close_a_pipelined_active_response():
    async def app(scope, receive, send):
        if scope["path"] == "/slow":
            await asyncio.sleep(0.4)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-length", b"2")]})
        await send({"type": "http.response.body", "body": b"ok"})

    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    errors = []
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, http="h11", lifespan="off",
        timeout_keep_alive=0.1, log_level="critical", access_log=False,
    ))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    writer = None
    try:
        async with asyncio.timeout(3):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.005)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /fast HTTP/1.1\r\nHost: local\r\n\r\n"
                     b"GET /slow HTTP/1.1\r\nHost: local\r\nConnection: close\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), 2)
        assert data.count(b"HTTP/1.1 200") == 2
        assert not errors
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        server.should_exit = True
        await asyncio.wait_for(task, 3)
        sock.close()
        loop.set_exception_handler(previous_handler)
