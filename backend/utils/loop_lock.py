"""按事件循环创建 asyncio.Lock。

两个坑：
- `threading.Lock` 在 async 函数里被 hold 住并跨 await，会把事件循环线程阻塞住，
  持有锁的协程再也等不到恢复，直接死锁（链接重建就踩过）；
- 模块级 `asyncio.Lock()` 在同一进程的多个事件循环里复用会报 "bound to a different event loop"。

所以按 (事件循环, 名字) 取锁；用弱引用字典，循环销毁后锁跟着释放。
"""
import asyncio
import weakref

_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]]" = (
    weakref.WeakKeyDictionary()
)


def loop_lock(name: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    named = _locks.get(loop)
    if named is None:
        named = {}
        _locks[loop] = named
    lock = named.get(name)
    if lock is None:
        lock = asyncio.Lock()
        named[name] = lock
    return lock
