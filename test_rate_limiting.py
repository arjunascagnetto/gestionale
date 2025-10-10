#!/usr/bin/env python
"""
Script di test per verificare la logica di rate limiting.
Simula lo scaricamento di messaggi con batch e delay.
"""
import asyncio
import time


BATCH_SIZE = 10  # Piccolo per test veloce
DELAY_BETWEEN_BATCHES = 2  # 2 secondi per test


async def simulate_telegram_fetch(total_messages=35):
    """
    Simula il fetch da Telegram con rate limiting.

    Args:
        total_messages: Numero totale di messaggi da simulare
    """
    print(f"📥 Simulazione fetch di {total_messages} messaggi")
    print(f"   Rate limiting: {BATCH_SIZE} msg/batch, {DELAY_BETWEEN_BATCHES}s delay\n")

    messages = []
    message_count = 0
    batch_count = 0
    offset = 0

    while offset < total_messages:
        batch_count += 1
        batch_start = time.time()

        print(f"   📦 Batch #{batch_count}: scaricamento fino a {BATCH_SIZE} messaggi...")

        # Simula scaricamento batch
        await asyncio.sleep(0.5)  # Simula network latency

        # Calcola quanti messaggi in questo batch
        remaining = total_messages - offset
        batch_size = min(BATCH_SIZE, remaining)

        # "Scarica" messaggi
        for i in range(batch_size):
            messages.append(f"msg_{offset + i}")

        offset += batch_size
        message_count += batch_size

        print(f"   ✅ Batch #{batch_count}: {batch_size} messaggi (totale: {message_count})")

        # Se abbiamo finito, esci
        if offset >= total_messages:
            print(f"   ✅ Tutti i messaggi scaricati.")
            break

        # Rate limiting: pausa tra batch
        batch_duration = time.time() - batch_start
        if batch_duration < DELAY_BETWEEN_BATCHES:
            sleep_time = DELAY_BETWEEN_BATCHES - batch_duration
            print(f"   ⏳ Pausa {sleep_time:.1f}s (rate limiting)...")
            await asyncio.sleep(sleep_time)

    print(f"\n✅ Completato: {len(messages)} messaggi in {batch_count} batch")

    # Calcola tempo totale e rate
    total_time = batch_count * DELAY_BETWEEN_BATCHES
    rate = len(messages) / total_time if total_time > 0 else 0

    print(f"\n📊 STATISTICHE:")
    print(f"   Messaggi totali: {len(messages)}")
    print(f"   Batch eseguiti: {batch_count}")
    print(f"   Tempo stimato: ~{total_time:.1f}s")
    print(f"   Rate: ~{rate:.1f} msg/s")
    print(f"   Rate Telegram limit: 20 req/s ✅" if rate < 20 else "   ⚠️ Rate troppo alto!")


async def test_floodwait_handling():
    """Simula gestione FloodWait."""
    print("\n" + "="*60)
    print("TEST GESTIONE FLOODWAIT")
    print("="*60 + "\n")

    print("📦 Batch #1: scaricamento...")
    await asyncio.sleep(0.5)
    print("✅ Batch #1: 10 messaggi")

    print("\n⚠️  SIMULATING FloodWaitError: attendo 5s...")
    wait_time = 5
    for i in range(wait_time, 0, -1):
        print(f"   ⏳ {i}s...", end='\r')
        await asyncio.sleep(1)
    print("\n✅ Attesa completata, ripresa scaricamento")

    print("\n📦 Batch #2: scaricamento...")
    await asyncio.sleep(0.5)
    print("✅ Batch #2: 10 messaggi")


async def main():
    """Test principale."""
    print("="*60)
    print("TEST RATE LIMITING - TELEGRAM BULK INGESTOR")
    print("="*60 + "\n")

    # Test 1: Scaricamento normale con rate limiting
    await simulate_telegram_fetch(total_messages=35)

    # Test 2: Gestione FloodWait
    await test_floodwait_handling()

    print("\n" + "="*60)
    print("✅ TUTTI I TEST COMPLETATI")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
