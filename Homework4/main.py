
import threading
import multiprocessing
import queue
import time

#kept these values separate so I can change the workload without touching the rest of the code
PRODUCERS = 3
CONSUMERS = 3
ITEMS_PER_PRODUCER = 5
BUFFER_SIZE = 2


def producer(number, buffer):
    for item in range(ITEMS_PER_PRODUCER):
        #used a tuple so i can tell which producer created each item
        #put also blocks when the buffer is full, so i don't need to manually check its size
        buffer.put((number, item))
        print(f"[producer {number}] produced item {item}", flush=True)


def consumer(number, buffer, results):
    consumed = 0
    while True:
        #get blocks when the buffer is empty instead of wasting cpu by constantly checking
        item = buffer.get()

        #i used none as a stop signal so consumers know when no more work is coming
        if item is None:
            #i still mark the stop signal as done so buffer.join() doesn't wait forever
            buffer.task_done()
            print(f"[consumer {number}] received stop signal - exiting", flush=True)
            break

        producer_number, item_number = item
        print(f"[consumer {number}] consumed item {item_number} from producer {producer_number}", flush=True)
        consumed += 1

        #this tells the queue that the item was processed, not just removed
        buffer.task_done()

    #i send each consumer's count back so i can verify that no items were lost
    results.put(consumed)


def run_threading():
    #queue handles locking for me and maxsize prevents producers from overflowing the buffer
    buffer = queue.Queue(maxsize=BUFFER_SIZE)
    results = queue.Queue()

    producers = [threading.Thread(target=producer, args=(i, buffer)) for i in range(1, PRODUCERS + 1)]
    consumers = [threading.Thread(target=consumer, args=(i, buffer, results)) for i in range(1, CONSUMERS + 1)]

    #i used perf_counter here because it measures elapsed time more precisely
    start = time.perf_counter()

    #start consumers too so they can process items as producers add them
    for worker in consumers + producers:
        worker.start()

    #i wait for every producer before sending stop signals so no items arrive after shutdown starts
    for worker in producers:
        worker.join()

    #each consumer needs its own stop signal or some could stay blocked on get forever
    for _ in consumers:
        buffer.put(None)

    #this waits until every item and stop signal has been marked as done
    buffer.join()

    #i join the consumers too so the program doesn't exit while any are still running
    for worker in consumers:
        worker.join()

    elapsed = time.perf_counter() - start

    #i add the individual counts to make sure all produced items were consumed
    total = sum(results.get() for _ in consumers)

    print(f"all producers finished, all consumers finished, {buffer.qsize()} items left")
    print(f"Produced: {PRODUCERS * ITEMS_PER_PRODUCER}, consumed: {total}")
    print(f"Threading time: {elapsed:.4f} seconds\n")
    return elapsed


def run_multiprocessing():
    #i used joinable queue because processes don't share a normal python queue or memory
    #this also lets me use task_done and join to track when all work is finished
    buffer = multiprocessing.JoinableQueue(maxsize=BUFFER_SIZE)
    results = multiprocessing.Queue()

    #the producer and consumer logic stays the same, but each worker now runs in its own process
    producers = [multiprocessing.Process(target=producer, args=(i, buffer)) for i in range(1, PRODUCERS + 1)]
    consumers = [multiprocessing.Process(target=consumer, args=(i, buffer, results)) for i in range(1, CONSUMERS + 1)]

    #i use the same timing method so i can compare both versions
    start = time.perf_counter()

    for worker in consumers + producers:
        worker.start()

    #here I wait for producers to finish before telling consumers to stop
    for worker in producers:
        worker.join()

    #one stop signal per consumer prevents processes from waiting forever
    for _ in consumers:
        buffer.put(None)

    #i wait for all queued work to finish before joining the processes
    buffer.join()

    for worker in consumers:
        worker.join()

    elapsed = time.perf_counter() - start
    total = sum(results.get() for _ in consumers)

    print("all producers finished, all consumers finished, 0 items left")
    print(f"Produced: {PRODUCERS * ITEMS_PER_PRODUCER}, consumed: {total}")
    print(f"Multiprocessing time: {elapsed:.4f} seconds\n")

    #close the multiprocessing queues to release their resources after everything finishes
    buffer.close()
    results.close()
    return elapsed


#this prevents child processes from running the main program again when they start
if __name__ == "__main__":
    print("=== Threading ===")
    run_threading()
    print("=== Multiprocessing ===")
    run_multiprocessing()
