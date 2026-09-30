"""At-most-once, at-least-once, and an idempotent consumer, with a crash in the middle.

A billing consumer charges the credit card for each order of photo prints. The consumer
crashes once while it processes order 4. Then a new instance continues in the same consumer
group from the last committed offset. Start Kafka first (`docker compose up -d kafka`).
"""

import json
import uuid

from common import consumer, ensure_topics, producer, send

ORDERS = [{"order": i, "user": 54351, "prints": i % 3 + 1} for i in range(1, 9)]


class Crash(Exception):
    pass


class PaymentService:
    def __init__(self, idempotent: bool):
        self.idempotent, self.charges, self.keys = idempotent, [], set()

    def charge(self, order: int) -> None:
        if self.idempotent and order in self.keys:
            return  # the same idempotency key again: no second charge
        self.keys.add(order)
        self.charges.append(order)


def billing(mode: str, topic: str) -> list[int]:
    payments = PaymentService(idempotent=mode == "idempotent")
    crashed = False
    for _instance in (1, 2):  # the first instance crashes, the second one continues
        c = consumer(f"billing-{mode}", [topic], verbose=False, **{"enable.auto.commit": False})
        try:
            while True:
                msg = c.poll(10)
                order = json.loads(msg.value())["order"]
                if mode == "at-most-once":
                    c.commit(msg, asynchronous=False)  # mark as done before the work
                if order == 4 and not crashed and mode == "at-most-once":
                    crashed = True
                    raise Crash  # crash before the charge
                payments.charge(order)
                if order == 4 and not crashed:
                    crashed = True
                    raise Crash  # crash after the charge, before the commit
                if mode != "at-most-once":
                    c.commit(msg, asynchronous=False)  # mark as done after the work
                if order == ORDERS[-1]["order"]:
                    return payments.charges
        except Crash:
            pass  # the process dies: no commit
        finally:
            c.close()
    return payments.charges


if __name__ == "__main__":
    print(f"{len(ORDERS)} orders; the consumer crashes once while it processes order 4.\n")
    print(f"{'mode':<14} {'charged orders':<28} {'lost':<6} {'charged twice'}")
    for mode in ["at-most-once", "at-least-once", "idempotent"]:
        topic = f"print_orders_{uuid.uuid4().hex[:8]}"
        ensure_topics({topic: 1})
        p = producer()
        for o in ORDERS:
            send(p, topic, o["order"], o)
        p.flush()
        charges = billing(mode, topic)
        lost = sorted({o["order"] for o in ORDERS} - set(charges))
        twice = sorted({c for c in charges if charges.count(c) > 1})
        print(f"{mode:<14} {str(charges):<28} {str(lost):<6} {twice}")
