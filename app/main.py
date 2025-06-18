import argparse
import multiprocessing as mp
from queue import Empty
from pathlib import Path
import cv2
from paddleocr import PaddleOCR
from PIL import Image
import logging
import json
from extract_all_fields import extract_all_fields

class OCRWorker(mp.Process):
    def __init__(self, queue_in, queue_out, config):
        super().__init__()
        self.queue_in = queue_in
        self.queue_out = queue_out
        self.config = config
        self.ocr_engine = None

    def initialize_ocr(self):
        self.ocr_engine = PaddleOCR(
            lang='en',
            cpu_threads=self.config['num_cpu_threads'],
            device = 'cpu',
            rec_batch_num=self.config['batch_size'],
            use_textline_orientation=False,
            text_detection_model_name="PP-OCRv3_mobile_det",
            text_recognition_model_name="PP-OCRv3_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False
        )

    
    def process_image(self, image_path):
        try:
            img = cv2.imread(str(image_path))
            raw_result = self.ocr_engine.predict(img)

            processed_fields = extract_all_fields(raw_result[0]) if raw_result else {}
            raw_texts = [line[1][0] for line in raw_result[0]] if raw_result else []

            return {
                'path': str(image_path),
                'raw_result': raw_result[0],               
                'processed_fields': processed_fields,       
                'raw_texts': raw_texts,                     
                'success': True
            }

        except Exception as e:
            return {
                'path': str(image_path),
                'error': str(e),
                'success': False
            }
        
    def run(self):
        self.initialize_ocr()
        while True:
            try:
                item = self.queue_in.get(timeout=60)
                if item is None:
                    break
                result = self.process_image(item)
                self.queue_out.put(result)
            except Empty:
                continue
            except Exception as e:
                logging.error(f"Worker error: {str(e)}")
                continue

class OCRProcessor:
    def __init__(self, num_workers=4):
        self.num_workers = num_workers
        self.config = {
            'num_cpu_threads': mp.cpu_count(),
            'batch_size': 32,
            'queue_size': 1000
        }
        self.work_queue = mp.Queue(maxsize=self.config['queue_size'])
        self.result_queue = mp.Queue()
        self.workers = []

    def start_workers(self):
        for _ in range(self.num_workers):
            worker = OCRWorker(self.work_queue, self.result_queue, self.config)
            worker.start()
            self.workers.append(worker)

    def stop_workers(self):
        for _ in range(self.num_workers):
            self.work_queue.put(None)
        for worker in self.workers:
            worker.join()

    def process_directory(self, input_path, output_path):
        input_path = Path(input_path)
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        images = [p for p in input_path.rglob('*') if p.suffix.lower() in image_extensions]

        for img_path in images:
            self.work_queue.put(str(img_path))

        total_images = len(images)
        processed = 0
        results = {}

        while processed < total_images:
            try:
                result = self.result_queue.get(timeout=60)
                results[result['path']] = result

                if result['success']:
                    print(f"✅ {processed + 1}/{total_images}: {result['path']}")
                else:
                    print(f"❌ {result['path']}: {result['error']}")

                processed += 1
            except Empty:
                continue

        # Save results to JSON
        output_file = output_path / "ocr_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n📄 Results saved to: {output_file}")

def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Batch OCR using PaddleOCR")
    parser.add_argument('input_dir', type=str, help="Input directory with images")
    parser.add_argument('output_dir', type=str, help="Directory to save OCR results")
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    if not input_path.exists() or not input_path.is_dir():
        print(f"❌ Invalid input directory: {input_path}")
        exit(1)

    processor = OCRProcessor(num_workers=mp.cpu_count())
    processor.start_workers()

    try:
        processor.process_directory(args.input_dir, args.output_dir)
    finally:
        processor.stop_workers()

if __name__ == '__main__':
    main()
