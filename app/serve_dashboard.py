from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import os
import json
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime

from pathlib import Path
from typing import List, Dict, Any
from pydantic import BaseModel

app = FastAPI()

API_KEY = "FGfEHRbtkWq7BHhb!8NJHHB9h9h78gK7Lasx0fEE*TknpHOZ"

# Constants
IMAGE_DIR = Path("./test_images")
OCR_JSON_PATH = Path("./output/ocr_results.json")
RESULTS_DIR = Path("./output/batch_results")

# Create results directory if it doesn't exist
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key_cookie = request.cookies.get("DASHBOARD_API_KEY")
        if api_key_cookie != API_KEY:
            html_path = Path(__file__).parent / "front.html"
            if html_path.exists():
                return FileResponse(html_path,401)
            return JSONResponse(content={"error": "Unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

# Pydantic models for request validation
class FieldResult(BaseModel):
    field: str |None
    value: str | None
    status: bool | None

class ImageResult(BaseModel):
    imageName: str
    fields: List[FieldResult]

class BatchSubmissionRequest(BaseModel):
    results: List[ImageResult]

def load_ocr_data() -> Dict[str, Any]:
    """Load OCR data from JSON file"""
    try:
        with open(OCR_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_ocr_data(data: Dict[str, Any]) -> bool:
    """Save OCR data to JSON file"""
    try:
        with open(OCR_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving OCR data: {e}")
        return False

# Utility to paginate images
def get_image_batch(start: int, end: int) -> List[dict]:
    ocr_data = load_ocr_data()

    images = sorted([
        file for file in IMAGE_DIR.iterdir()
        if file.suffix.lower() in {'.jpg', '.jpeg', '.png'}
    ])

    batch = []
    for img_path in images[start:end]:
        rel_path = str(img_path).replace("\\", "/")  # for Windows compatibility
        ocr_entry = ocr_data.get(rel_path, {})
        processed_fields = ocr_entry.get("processed_fields", {})
        
        # Check if this image has user ratings
        user_ratings = ocr_entry.get("user_ratings", {})
        is_graded = len(user_ratings) > 0
        graded_at = ocr_entry.get("graded_at", None)
        
        batch.append({
            "filename": img_path.name,
            "image_url": f"/image/{img_path.name}",
            "processed_fields": processed_fields,
            "is_graded": is_graded,
            "graded_at": graded_at,
            "user_ratings": user_ratings
        })

    return batch

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html_path = Path(__file__).parent / "front.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse(content="<h1>front.html not found</h1>", status_code=404)

@app.get("/api/batch")
def get_batch(page: int = 1, page_size: int = 10):
    start = (page - 1) * page_size
    end = start + page_size
    batch = get_image_batch(start, end)
    return JSONResponse(content={"data": batch})


@app.get("/image/{filename}")
def serve_image(filename: str):
    img_path = IMAGE_DIR / filename
    if img_path.exists():
        return FileResponse(img_path)
    return JSONResponse(content={"error": "Image not found"}, status_code=404)


@app.get("/api/stats")
def get_stats():
    """Get overall grading statistics"""
    try:
        ocr_data = load_ocr_data()
        total_images = len([key for key in ocr_data.keys() if key.startswith("test_images/")])
        graded_images = len([key for key, value in ocr_data.items() 
                           if key.startswith("test_images/") and value.get("user_ratings")])
        
        return JSONResponse(content={
            "total_images": total_images,
            "graded_images": graded_images,
            "completion_percentage": round((graded_images / total_images * 100), 2) if total_images > 0 else 0
        })
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to get stats: {str(e)}"}, 
            status_code=500
        )


@app.post("/api/batch/submit")
def submit_batch_grades(request: BatchSubmissionRequest):
    """
    Submit all grades and save them to the OCR results file and a timestamped batch results file
    """
    try:
        # Load existing OCR data
        ocr_data = load_ocr_data()
        
        # Create a timestamp for this batch submission
        timestamp = datetime.now().isoformat()
        
        # Process each image result
        updated_images = []
        batch_results = {
            "submission_timestamp": timestamp,
            "total_images": len(request.results),
            "results": []
        }
        
        for image_result in request.results:
            # Find the corresponding OCR entry
            image_key = None
            for key in ocr_data.keys():
                if key.endswith(image_result.imageName):
                    image_key = key
                    break
            
            if not image_key:
                # If not found, create a new entry
                image_key = f"test_images/{image_result.imageName}"
                ocr_data[image_key] = {"processed_fields": {}}
            
            # Update user ratings
            user_ratings = {}
            field_results = []
            
            for field in image_result.fields:
                if field.status is not None:
                    user_ratings[field.field] = {
                        "is_correct": field.status,
                        "timestamp": timestamp
                    }
                    
                field_results.append({
                    "field": field.field,
                    "predicted_value": field.value,
                    "user_rating": field.status,
                    "is_correct": field.status
                })
            
            # Update OCR data
            ocr_data[image_key]["user_ratings"] = user_ratings
            ocr_data[image_key]["graded_at"] = timestamp
            ocr_data[image_key]["is_graded"] = True
            
            # Add to batch results
            batch_results["results"].append({
                "image_name": image_result.imageName,
                "image_path": image_key,
                "total_fields": len(image_result.fields),
                "graded_fields": len([f for f in image_result.fields if f.status is not None]),
                "correct_fields": len([f for f in image_result.fields if f.status is True]),
                "incorrect_fields": len([f for f in image_result.fields if f.status is False]),
                "accuracy": round(len([f for f in image_result.fields if f.status is True]) / max(len([f for f in image_result.fields if f.status is not None]), 1) * 100, 2),
                "fields": field_results
            })
            
            updated_images.append(image_result.imageName)
        
        # Calculate overall batch statistics
        total_fields = sum(len(result["fields"]) for result in batch_results["results"])
        total_correct = sum(result["correct_fields"] for result in batch_results["results"])
        overall_accuracy = round(total_correct / max(total_fields, 1) * 100, 2) if total_fields > 0 else 0
        
        batch_results["summary"] = {
            "total_fields_reviewed": total_fields,
            "total_correct_fields": total_correct,
            "total_incorrect_fields": sum(result["incorrect_fields"] for result in batch_results["results"]),
            "overall_accuracy": overall_accuracy,
            "images_processed": len(updated_images)
        }
        
        # Save updated OCR data
        if not save_ocr_data(ocr_data):
            return JSONResponse(
                content={"error": "Failed to save OCR data"}, 
                status_code=500
            )
        
        # Save batch results to a timestamped file
        batch_filename = f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        batch_file_path = RESULTS_DIR / batch_filename
        
        try:
            with open(batch_file_path, 'w', encoding='utf-8') as f:
                json.dump(batch_results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save batch results file: {e}")
            # Continue execution even if batch file save fails
        
        # Also save/update a latest results file for easy access
        latest_file_path = RESULTS_DIR / "latest_batch_results.json"
        try:
            with open(latest_file_path, 'w', encoding='utf-8') as f:
                json.dump(batch_results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save latest results file: {e}")
        
        return JSONResponse(content={
            "message": "Batch grades submitted successfully",
            "updated_images": updated_images,
            "total_images": len(updated_images),
            "updated_ocr_file": str(OCR_JSON_PATH),
            "batch_results_file": str(batch_file_path),
            "summary": batch_results["summary"],
            "timestamp": timestamp
        })
        
    except Exception as e:
        print(f"Error in submit_batch_grades: {e}")
        return JSONResponse(
            content={"error": f"Failed to submit grades: {str(e)}"}, 
            status_code=500
        )


@app.get("/api/batch/results")
def get_batch_results():
    """
    Get the latest batch results
    """
    try:
        latest_file_path = RESULTS_DIR / "latest_batch_results.json"
        
        if not latest_file_path.exists():
            return JSONResponse(
                content={"error": "No batch results found"}, 
                status_code=404
            )
        
        with open(latest_file_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        return JSONResponse(content=results)
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to get batch results: {str(e)}"}, 
            status_code=500
        )


@app.get("/api/batch/history")
def get_batch_history():
    """
    Get list of all batch result files
    """
    try:
        batch_files = []
        
        for file_path in RESULTS_DIR.glob("batch_results_*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                batch_files.append({
                    "filename": file_path.name,
                    "timestamp": data.get("submission_timestamp"),
                    "total_images": data.get("total_images", 0),
                    "overall_accuracy": data.get("summary", {}).get("overall_accuracy", 0),
                    "file_path": str(file_path)
                })
            except Exception as e:
                print(f"Error reading batch file {file_path}: {e}")
                continue
        
        # Sort by timestamp (newest first)
        batch_files.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return JSONResponse(content={"batch_history": batch_files})
        
    except Exception as e:
        return JSONResponse(
            content={"error": f"Failed to get batch history: {str(e)}"}, 
            status_code=500
        )