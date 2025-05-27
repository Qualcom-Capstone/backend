# ocr.py
import requests
from io import BytesIO
from PIL import Image  # Pillow Image 사용
import cv2
import numpy as np
import easyocr
import re
import uuid
import os
from django.conf import settings

# 1. OCR 리더 초기화 및 설정 (기존 코드 유지)
OCR_READER = None  #
OCR_INIT_ERROR = None  #
try:  #
    OCR_READER = easyocr.Reader(['ko', 'en'], gpu=False)  #
    print("EasyOCR Reader initialized successfully (in ocr_processors).")  #
except Exception as e:  #
    OCR_INIT_ERROR = f"EasyOCR Reader 초기화 실패 (ocr_processors): {e}"  #
    print(f"CRITICAL: {OCR_INIT_ERROR}")  #

CHAR_CORRECTION_MAP = {  #
    'I': '1', 'L': '1', 'O': '0', 'Q': '0', 'Z': '2', 'E': '3',  #
    'A': '4', 'S': '5', 'G': '6', 'T': '7', 'B': '8',  #
}  #


# 2. 디버그 이미지 저장 함수 (개선된 버전 - File 2 of 6 from prompt 기준)
def _save_cv_image_for_debugging(cv_image, step_name: str, operation_id: str, original_filename_hint="debug_img"):  #
    if cv_image is None or cv_image.size == 0:  #
        print(f"Debug Save Error: '{step_name}' 이미지 데이터가 없어 저장할 수 없습니다.")  #
        return None  #
    try:  #
        vehicle_id_base = os.path.splitext(os.path.basename(original_filename_hint))[0]  #
        safe_vehicle_id_folder_name = re.sub(r'[^\w-]', '_', vehicle_id_base)[:50]  #
        session_id_folder_name = operation_id[:8]  #
        base_ocr_debug_dir = os.path.join(settings.MEDIA_ROOT, 'ocr_debug_steps')  #
        vehicle_specific_dir = os.path.join(base_ocr_debug_dir, safe_vehicle_id_folder_name)  #
        session_specific_dir = os.path.join(vehicle_specific_dir, session_id_folder_name)  #
        os.makedirs(session_specific_dir, exist_ok=True)  #
        safe_step_name = re.sub(r'[^\w-]', '_', step_name)  #
        filename = f"{safe_step_name}.png"  #
        full_save_path = os.path.join(session_specific_dir, filename)  #
        if not os.path.abspath(full_save_path).startswith(os.path.abspath(settings.MEDIA_ROOT)):  #
            print(f"Security Alert: MEDIA_ROOT 외부 저장 시도: {full_save_path}")  #
            return None  #
        cv2.imwrite(full_save_path, cv_image)  #
        print(f"Debug Image Saved: '{step_name}' at {full_save_path}")  #
        return os.path.relpath(full_save_path, settings.MEDIA_ROOT)  #
    except Exception as e:  #
        print(f"Debug Image Save Error ('{step_name}'): {type(e).__name__} - {e}")  #
        return None  #


# 3. 내부 OCR 헬퍼 함수들 (기존 코드 유지 - File 2 of 6 from prompt 기준)
def _internal_run_ocr(cv_image):  #
    if not OCR_READER: return []  #
    try:  #
        return OCR_READER.readtext(cv_image)  #
    except Exception as e:  #
        print(f"Error in _internal_run_ocr: {e}")  #
        return []  #


def _internal_select_license_plate_candidate(ocr_results):  #
    selected_bbox, best_text, best_prob = None, "", 0.0  #
    longest_len, fallback_bbox, fallback_text = 0, None, ""  #
    if not ocr_results: return None, ""  #
    for (bbox_coords, text_content, confidence) in ocr_results:  #
        cleaned = re.sub(r'[\s\W_]+', '', text_content)  #
        if re.search(r'\d', cleaned) and re.search(r'[가-힣]', cleaned) and 3 <= len(cleaned) <= 7:  #
            if confidence > best_prob:  #
                best_prob, selected_bbox, best_text = confidence, bbox_coords, text_content  #
    if not selected_bbox:  #
        for (bbox_coords, text_content, confidence) in ocr_results:  #
            cleaned = re.sub(r'[\s\W_]+', '', text_content)  #
            if 3 <= len(cleaned) <= 8 and len(cleaned) > longest_len:  #
                longest_len, fallback_bbox, fallback_text = len(cleaned), bbox_coords, text_content  #
        if fallback_bbox:  #
            selected_bbox, best_text = fallback_bbox, fallback_text  #
    return selected_bbox, best_text  #


def _internal_crop_plate_region(image_cv, bbox, trim_ratio_each_side=0.02, vertical_padding=3):  #
    if bbox is None or image_cv is None: return None  #
    x_coords = [int(p[0]) for p in bbox]  #
    y_coords = [int(p[1]) for p in bbox]  #
    x_min, x_max = min(x_coords), max(x_coords)  #
    y_min, y_max = min(y_coords), max(y_coords)  #
    width = x_max - x_min  #
    if width <= 0:  #
        return image_cv[y_min:y_max, x_min:x_max] if y_min < y_max and x_min < x_max else None  #
    offset = int(width * trim_ratio_each_side)  #
    x_min_t, x_max_t = x_min + offset, x_max - offset  #
    y_min_f = max(0, y_min - vertical_padding)  #
    y_max_f = min(image_cv.shape[0], y_max + vertical_padding)  #
    if x_min_t >= x_max_t or y_min_f >= y_max_f:  #
        cropped_image = image_cv[y_min:y_max, x_min:x_max]  #
    else:  #
        cropped_image = image_cv[y_min_f:y_max_f, x_min_t:x_max_t]  #
    return cropped_image if cropped_image.size > 0 else None  #


def _internal_preprocess_cropped_plate(cropped_image_cv):  #
    if cropped_image_cv is None: return None  #
    try:  #
        if len(cropped_image_cv.shape) == 2 or cropped_image_cv.shape[2] == 1:  #
            gray_img = cropped_image_cv  #
        else:  #
            gray_img = cv2.cvtColor(cropped_image_cv, cv2.COLOR_BGR2GRAY)  #
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(11, 11))  #
        enhanced_crop = clahe.apply(gray_img)  #
        return enhanced_crop  #
    except cv2.error as e:  #
        print(f"OpenCV error during plate preprocessing: {e}. Returning original or None.")  #
        if len(cropped_image_cv.shape) == 2: return cropped_image_cv  #
        try:  #
            return cv2.cvtColor(cropped_image_cv, cv2.COLOR_BGR2GRAY)  #
        except:  #
            return None  #


def _internal_correct_text(text_in):  #
    if not text_in: return ""  #
    text = text_in.replace(" ", "").strip().upper()  #
    char_list = list(text)  #
    for i in range(min(2, len(char_list))):  #
        if 'A' <= char_list[i] <= 'Z' and char_list[i] in CHAR_CORRECTION_MAP:  #
            char_list[i] = CHAR_CORRECTION_MAP[char_list[i]]  #
    if len(char_list) > 2:  #
        for i in range(min(4, len(char_list))):  #
            idx = len(char_list) - 1 - i  #
            if idx < 0: break  #
            if 'A' <= char_list[idx] <= 'Z' and char_list[idx] in CHAR_CORRECTION_MAP:  #
                char_list[idx] = CHAR_CORRECTION_MAP[char_list[idx]]  #
    return "".join(char_list)  #


# 4. 메인 OCR 처리 함수 (PIL 이미지 입력으로 수정)
def process_pil_image_roi_for_plate_ocr(
        pil_image: Image.Image,  # PIL 이미지 객체
        x_rel: float, y_rel: float, w_rel: float, h_rel: float,  # ROI 상대 좌표
        image_file_name_hint: str = "pil_image"  # 파일명 힌트
) -> dict:
    """
    PIL 이미지와 ROI 좌표를 받아, 해당 영역에서 번호판을 찾아 OCR을 수행합니다.
    1. (입력된 PIL 이미지를 OpenCV 이미지로 변환)
    2. ROI 자르기 (좌표 기반) -> 저장
    3. ROI에서 번호판 영역 자르기 -> 저장
    4. 번호판 이미지 전처리 -> 저장
    5. 번호판 OCR 및 번호 추출
    """
    operation_id = uuid.uuid4().hex  #
    debug_paths = {}  #
    default_plate_number = "12가1234"  #

    if OCR_INIT_ERROR:  #
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': f"OCR 엔진 오류: {OCR_INIT_ERROR}"}  #
    if not OCR_READER:  #
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': "OCR 엔진 사용 불가"}  #

    try:
        original_cv_image = np.array(pil_image.convert('RGB'))  #
        original_cv_image = original_cv_image[:, :, ::-1].copy()  #
    except Exception as e:
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': f"이미지 변환 오류 (PIL to CV): {e}"}

    # 원본 이미지 저장 (디버깅용)
    debug_paths['00_original_image_from_pil'] = _save_cv_image_for_debugging(
        original_cv_image, "original_from_pil", operation_id, image_file_name_hint
    )

    # --- 2. 좌표 값을 토대로 해당 이미지(ROI) 자르기 ---
    img_height, img_width = original_cv_image.shape[:2]  #
    if not (0.0 <= x_rel < 1.0 and 0.0 <= y_rel < 1.0 and \
            0.0 < w_rel <= 1.0 and 0.0 < h_rel <= 1.0 and \
            x_rel + w_rel <= 1.00001 and y_rel + h_rel <= 1.00001):  #
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': "제공된 ROI 좌표가 유효 범위를 벗어남"}  #

    abs_x = int(x_rel * img_width)  #
    abs_y = int(y_rel * img_height)  #
    abs_width = int(w_rel * img_width)  #
    abs_height = int(h_rel * img_height)  #

    if abs_width <= 0 or abs_height <= 0:  #
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': "계산된 ROI 너비 또는 높이가 0 이하"}  #

    roi_cv_image = original_cv_image[abs_y: abs_y + abs_height, abs_x: abs_x + abs_width]  #
    if roi_cv_image.size == 0:  #
        return {'car_number': None, 'debug_image_paths': debug_paths, 'error': "ROI 자르기 실패 (결과 이미지 크기 0)"}  #

    debug_paths['01_roi_cropped'] = _save_cv_image_for_debugging(  #
        roi_cv_image, "roi_crop", operation_id, image_file_name_hint
    )

    # --- 3. 잘린 이미지(ROI)를 토대로 번호판 영역 자르기 ---
    ocr_results_on_roi = _internal_run_ocr(roi_cv_image)  #
    if not ocr_results_on_roi:  #
        return {'car_number': default_plate_number, 'debug_image_paths': debug_paths, 'error': "ROI 내에서 텍스트 미발견"}  #

    plate_bbox_in_roi, initial_plate_text = _internal_select_license_plate_candidate(ocr_results_on_roi)  #

    plate_cv_image = None  #
    if plate_bbox_in_roi:  #
        plate_cv_image = _internal_crop_plate_region(roi_cv_image, plate_bbox_in_roi)  #
        if plate_cv_image is not None:  #
            debug_paths['02_plate_cropped_from_roi'] = _save_cv_image_for_debugging(  #
                plate_cv_image, "plate_crop_from_roi", operation_id, image_file_name_hint
            )
        else:  #
            print("ROI에서 번호판 영역 자르기 실패, 초기 후보 텍스트 사용 시도.")  #
    else:  #
        print("ROI 내에서 번호판 영역 특정 실패, ROI 전체 텍스트로 번호판 추출 시도.")  #

    # --- 4. 번호판 이미지를 간단히 전처리하기 ---
    target_for_final_ocr = None  #
    if plate_cv_image is not None:  #
        enhanced_plate_cv = _internal_preprocess_cropped_plate(plate_cv_image)  #
        if enhanced_plate_cv is not None:  #
            debug_paths['03_enhanced_plate'] = _save_cv_image_for_debugging(  #
                enhanced_plate_cv, "enhanced_plate", operation_id, image_file_name_hint
            )
            target_for_final_ocr = enhanced_plate_cv  #
        else:  #
            print("번호판 이미지 전처리 실패, 원본 잘린 번호판 이미지로 OCR 시도.")  #
            target_for_final_ocr = plate_cv_image  #
            debug_paths['03_plate_crop_as_fallback'] = _save_cv_image_for_debugging(  #
                plate_cv_image, "plate_crop_fallback", operation_id, image_file_name_hint
            )
    elif initial_plate_text:  #
        print("번호판 영역 특정/자르기 실패. ROI에서 선택된 초기 텍스트로 번호 추출 시도.")  #
        final_car_number = _internal_correct_text(initial_plate_text)  #
        if final_car_number and len(final_car_number) >= 3:  #
            return {'car_number': final_car_number, 'debug_image_paths': debug_paths, 'error': None}  #
        else:  #
            return {'car_number': default_plate_number, 'debug_image_paths': debug_paths,  #
                    'error': "초기 후보 텍스트 교정 후 유효하지 않음"}  #
    else:  #
        return {'car_number': default_plate_number, 'debug_image_paths': debug_paths,  #
                'error': "번호판 영역 특정 및 초기 텍스트 확보 모두 실패"}  #

    # --- 5. 번호판 OCR 번호 추출 ---
    if target_for_final_ocr is None:  #
        return {'car_number': default_plate_number, 'debug_image_paths': debug_paths, 'error': "최종 OCR 대상 이미지 준비 실패"}  #

    final_ocr_results = _internal_run_ocr(target_for_final_ocr)  #
    raw_text_from_final_ocr = "".join([res[1] for res in final_ocr_results]) if final_ocr_results else ""  #
    final_raw_text_to_correct = raw_text_from_final_ocr if raw_text_from_final_ocr else initial_plate_text  #
    final_car_number = _internal_correct_text(final_raw_text_to_correct)  #

    if final_car_number and len(final_car_number) >= 3:  #
        return {'car_number': final_car_number, 'debug_image_paths': debug_paths, 'error': None}  #
    else:  #
        print(f"최종 차량 번호 유효하지 않음 ('{final_car_number}'). Defaulting to {default_plate_number}.")  #
        return {'car_number': default_plate_number, 'debug_image_paths': debug_paths, 'error': "최종 OCR 결과가 유효하지 않음"}  #

