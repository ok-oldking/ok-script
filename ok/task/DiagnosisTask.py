import os
import time

import psutil

from ok.task.task import BaseTask
from ok.util.collection import get_median
from ok.util.process import get_current_process_memory_usage


class DiagnosisTask(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Diagnosis"
        self.description = "Performance Test"

    def run(self):
        start = time.time()
        capture_total = 0
        ocr_total = 0
        cpu_readings = []
        pid = os.getpid()
        process = psutil.Process(pid)
        cores = psutil.cpu_count(logical=True)
        while True:
            self.info['Frame Count'] = self.info.get('Frame Count', 0) + 1
            self.info['Process Frame Rate'] = round(
                self.info['Frame Count'] / ((time.time() - start) or 1),
                2)
            self.info['Capture Frame Rate'] = round(
                self.info['Frame Count'] / (capture_total or 1),
                2)
            self.info['Game Resolution'] = f'{self.frame.shape[1]}x{self.frame.shape[0]}'
            if self.info['Frame Count'] == 1:
                self.ocr()  # warm up
            operation_start = time.time()
            boxes = self.ocr(threshold=0.1)
            ocr_total += time.time() - operation_start
            self.info['Texts'] = ",".join(box.name for box in boxes)
            self.info['Capture Latency'] = f"{round(1000 * capture_total / self.info['Frame Count'], 2)} ms"
            self.info['OCR Latency'] = f"{round(1000 * ocr_total / self.info['Frame Count'], 2)} ms"
            if self.info['Frame Count'] % 20 == 1:
                rss, vms, _ = get_current_process_memory_usage()  # We don't care about shm here
                self.info['Memory'] = f'{round(rss)} MB'

            cpu_usage = process.cpu_percent(interval=0)
            cpu_readings.append(cpu_usage)
            cpu_readings = cpu_readings[-20:]

            self.info['CPU'] = f"{round(get_median(cpu_readings) / cores, 2)}%"

            operation_start = time.time()
            self.next_frame()
            capture_total += time.time() - operation_start
