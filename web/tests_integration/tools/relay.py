"""호스트 루프백 8080 → 18080 단순 바이트 중계(헤더 불변).

nginx·백엔드는 Host 가 127.0.0.1:8080 인 요청만 받는다(포트 고정 설계, O-VI-09). 시험용 스택은 호스트 18080 에 게시되어 있어,
브라우저(Chromium)와 Node 의 fetch 가 자연스러운 Host/Origin(127.0.0.1:8080)을 보내려면 이 중계가 필요하다. 시험 도중에만 띄운다.
사용: python relay.py [listen_port=8080] [target_port=18080]
"""
import asyncio
import sys

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else 18080


async def pipe(r, w):
    try:
        while True:
            b = await r.read(65536)
            if not b:
                break
            w.write(b)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle(cr, cw):
    try:
        ur, uw = await asyncio.open_connection("127.0.0.1", TARGET)
    except Exception:
        cw.close()
        return
    await asyncio.gather(pipe(cr, uw), pipe(ur, cw))


async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", LISTEN)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
