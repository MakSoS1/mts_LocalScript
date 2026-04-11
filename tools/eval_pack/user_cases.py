from __future__ import annotations


FIRST_PACK_CASES = [
    {
        "id": "pack1_normalize_phone",
        "context": {"wf": {"vars": {"phone": "8 (999) 123-45-67"}}},
        "prompts": {
            "ru": "Из номера телефона клиента phone очисти все символы кроме цифр. Если номер начинается с 8 и содержит 11 цифр, замени первую цифру на 7. Верни результат в переменную normalizedPhone."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "normalizedPhone",
        "expected_lua_initial": """local phone = tostring(wf.vars.phone or "")
local digits = string.gsub(phone, "%D", "")
if string.len(digits) == 11 and string.sub(digits, 1, 1) == "8" then
  digits = "7" .. string.sub(digits, 2)
end
return digits""",
        "expected_runtime_initial": "79991234567",
    },
    {
        "id": "pack1_primary_email",
        "context": {
            "wf": {
                "vars": {
                    "contacts": [
                        {"type": "secondary", "email": "backup@example.com"},
                        {"type": "primary", "email": "main@example.com"},
                        {"type": "billing", "email": "bill@example.com"},
                    ]
                }
            }
        },
        "prompts": {
            "ru": "Из массива contacts найди email, у которого type = primary. Если такого нет, верни первый email из массива. Верни результат в primaryEmail."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "primaryEmail",
        "expected_lua_initial": """local contacts = wf.vars.contacts
for _, item in ipairs(contacts) do
  if item.type == "primary" and item.email ~= nil and item.email ~= "" then
    return item.email
  end
end
if contacts[1] ~= nil then
  return contacts[1].email
end
return nil""",
        "expected_runtime_initial": "main@example.com",
    },
    {
        "id": "pack1_clean_deals",
        "context": {
            "wf": {
                "vars": {
                    "deals": [
                        {
                            "ID": 101,
                            "TITLE": "Deal A",
                            "STAGE": "NEW",
                            "AMOUNT": 50000,
                            "CURRENCY": "RUB",
                            "OWNER": "Ivan",
                        },
                        {"ID": 102, "TITLE": "Deal B", "STAGE": "WON", "AMOUNT": 120000, "COMMENTS": "Important"},
                    ]
                }
            }
        },
        "prompts": {
            "ru": "Для массива deals из REST-ответа оставь в каждом объекте только поля ID, TITLE, STAGE и AMOUNT. Верни результат в cleanedDeals."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "cleanedDeals",
        "expected_lua_initial": """local result = wf.vars.deals
for _, item in pairs(result) do
  for key, value in pairs(item) do
    if key ~= "ID" and key ~= "TITLE" and key ~= "STAGE" and key ~= "AMOUNT" then
      item[key] = nil
    end
  end
end
return result""",
        "expected_runtime_initial": [
            {"ID": 101, "TITLE": "Deal A", "STAGE": "NEW", "AMOUNT": 50000},
            {"ID": 102, "TITLE": "Deal B", "STAGE": "WON", "AMOUNT": 120000},
        ],
    },
    {
        "id": "pack1_filter_active_leads",
        "context": {
            "wf": {
                "vars": {
                    "leads": [
                        {"id": 1, "status": "active", "email": "a@example.com", "phone": ""},
                        {"id": 2, "status": "new", "email": "", "phone": ""},
                        {"id": 3, "status": "active", "email": "", "phone": "+79990000000"},
                        {"id": 4, "status": "closed", "email": "b@example.com", "phone": ""},
                    ]
                }
            }
        },
        "prompts": {
            "ru": "Из массива leads оставь только активные заявки, у которых заполнен хотя бы один контакт: email или phone. Верни результат в filteredLeads."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "filteredLeads",
        "expected_lua_initial": """local result = _utils.array.new()
local leads = wf.vars.leads
for _, item in ipairs(leads) do
  local hasEmail = item.email ~= nil and item.email ~= ""
  local hasPhone = item.phone ~= nil and item.phone ~= ""
  if item.status == "active" and (hasEmail or hasPhone) then
    table.insert(result, item)
  end
end
return result""",
        "expected_runtime_initial": [
            {"id": 1, "status": "active", "email": "a@example.com", "phone": ""},
            {"id": 3, "status": "active", "email": "", "phone": "+79990000000"},
        ],
    },
    {
        "id": "pack1_normalize_lineitems",
        "context": {"wf": {"vars": {"order": {"id": "ORD-1", "lineItems": {"sku": "SKU-1", "qty": 2}}}}},
        "prompts": {
            "ru": "Сделай так, чтобы поле lineItems в order всегда было массивом. Если там один объект, оберни его в массив. Верни результат в normalizedItems."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "normalizedItems",
        "expected_lua_initial": """local items = wf.vars.order.lineItems
if type(items) ~= "table" then
  return {items}
end
local isArray = true
for k, v in pairs(items) do
  if type(k) ~= "number" or math.floor(k) ~= k then
    isArray = false
    break
  end
end
if isArray then
  return items
end
return {items}""",
        "expected_runtime_initial": [{"sku": "SKU-1", "qty": 2}],
    },
    {
        "id": "pack1_total_weight",
        "context": {
            "wf": {
                "vars": {
                    "packages": [
                        {"id": "P1", "weight": "10"},
                        {"id": "P2", "weight": "5.5"},
                        {"id": "P3", "weight": ""},
                    ]
                }
            }
        },
        "prompts": {"ru": "Посчитай суммарный weight всех элементов массива packages и верни значение в totalWeight."},
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "totalWeight",
        "expected_lua_initial": """local total = 0
for _, item in ipairs(wf.vars.packages) do
  local w = tonumber(item.weight)
  if w ~= nil then
    total = total + w
  end
end
return total""",
        "expected_runtime_initial": 15.5,
    },
    {
        "id": "pack1_approval_route",
        "context": {"wf": {"vars": {"amount": 150000, "region": "MSK"}}},
        "prompts": {
            "ru": "Определи approvalRoute по сумме amount и региону region. Если amount больше 100000 и region = MSK, верни senior_msk. Если amount больше 100000 и region не MSK, верни senior_regional. Во всех остальных случаях верни standard."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "approvalRoute",
        "expected_lua_initial": """local amount = tonumber(wf.vars.amount) or 0
local region = wf.vars.region
if amount > 100000 and region == "MSK" then
  return "senior_msk"
end
if amount > 100000 and region ~= "MSK" then
  return "senior_regional"
end
return "standard\"""".replace('\\"', '"'),
        "expected_runtime_initial": "senior_msk",
    },
    {
        "id": "pack1_notification_text",
        "context": {"wf": {"vars": {"request": {"ID": "REQ-77", "CLIENT_NAME": "ООО Вектор", "AMOUNT": "250000"}}}},
        "prompts": {"ru": "Собери строку notificationText в формате: Новая заявка <ID> от <CLIENT_NAME> на сумму <AMOUNT>."},
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "notificationText",
        "expected_lua_initial": """local id = tostring(wf.vars.request.ID or "")
local client = tostring(wf.vars.request.CLIENT_NAME or "")
local amount = tostring(wf.vars.request.AMOUNT or "")
return "Новая заявка " .. id .. " от " .. client .. " на сумму " .. amount""",
        "expected_runtime_initial": "Новая заявка REQ-77 от ООО Вектор на сумму 250000",
    },
    {
        "id": "pack1_retry_delay",
        "context": {"wf": {"vars": {"try_count_n": 12}}},
        "prompts": {
            "ru": "Посчитай задержку до следующей попытки retryDelaySec по формуле 30 * try_count_n. Максимальное значение 300. Верни результат в retryDelaySec."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "retryDelaySec",
        "expected_lua_initial": """local n = tonumber(wf.vars.try_count_n) or 0
local delay = 30 * n
if delay > 300 then
  delay = 300
end
return delay""",
        "expected_runtime_initial": 300,
    },
    {
        "id": "pack1_sla_escalation",
        "context": {"wf": {"initVariables": {"priority": "high", "overdue": True}}},
        "prompts": {
            "ru": "Если при запуске процесса из variables пришел priority = high и overdue = true, верни escalationNeeded = true, иначе false."
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "escalationNeeded",
        "expected_lua_initial": """local priority = wf.initVariables.priority
local overdue = wf.initVariables.overdue
if priority == "high" and overdue == true then
  return true
end
return false""",
        "expected_runtime_initial": True,
    },
]


SECOND_PACK_CASES = [
    {
        "id": "pack2_dedupe_phones",
        "context": {
            "wf": {
                "vars": {
                    "leads": [
                        {"id": 1, "name": "A", "phone": "8 (999) 123-45-67"},
                        {"id": 2, "name": "B", "phone": "+7 999 123 45 67"},
                        {"id": 3, "name": "C", "phone": ""},
                        {"id": 4, "name": "D", "phone": "8-921-000-11-22"},
                    ]
                }
            }
        },
        "prompts": {
            "ru": """Из массива leads убери дубликаты по номеру телефона.
Сначала очисти phone от всех символов кроме цифр.
Если номер начинается с 8 и содержит 11 цифр, замени первую цифру на 7.
Оставь только первую запись для каждого нормализованного номера.
Добавь в сохраненные записи поле normalizedPhone.
Верни результат в uniqueLeads.""",
            "en": """Deduplicate the leads array by phone number.
First remove all non-digit characters from phone.
If the number starts with 8 and has 11 digits, replace the first digit with 7.
Keep only the first record for each normalized phone number.
Add normalizedPhone to the kept records.
Return the result as uniqueLeads.""",
            "noisy": """У нас старый процесс загрузки лидов из нескольких источников, поэтому телефоны приходят в разном виде: где-то с пробелами, где-то с плюсами, где-то с дефисами.
Из-за этого в CRM появляются дубли и менеджеры тратят время на ручную сверку.
На текущем шаге процесса нужно сделать только техническую нормализацию перед следующим узлом.
Из массива leads убери дубликаты по номеру телефона, предварительно очистив phone от всех символов кроме цифр.
Если номер начинается с 8 и содержит 11 цифр, замени первую цифру на 7.
Оставь только первую запись для каждого нормализованного номера, добавь normalizedPhone и верни результат в uniqueLeads.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "uniqueLeads",
        "expected_lua_initial": """local result = _utils.array.new()
local seen = {}
for _, item in ipairs(wf.vars.leads) do
  local raw = tostring(item.phone or "")
  local digits = string.gsub(raw, "%D", "")
  if string.len(digits) == 11 and string.sub(digits, 1, 1) == "8" then
    digits = "7" .. string.sub(digits, 2)
  end
  if digits ~= "" and seen[digits] == nil then
    item.normalizedPhone = digits
    table.insert(result, item)
    seen[digits] = true
  end
end
return result""",
        "expected_runtime_initial": [
            {"id": 1, "name": "A", "phone": "8 (999) 123-45-67", "normalizedPhone": "79991234567"},
            {"id": 4, "name": "D", "phone": "8-921-000-11-22", "normalizedPhone": "79210001122"},
        ],
        "followup_user": "Нет, нужен другой ключ: deduplicatedLeads. Логику не меняй.",
        "expected_mode_followup": "json_with_lua_wrappers",
        "expected_output_key_followup": "deduplicatedLeads",
        "expected_lua_followup": """local result = _utils.array.new()
local seen = {}
for _, item in ipairs(wf.vars.leads) do
  local raw = tostring(item.phone or "")
  local digits = string.gsub(raw, "%D", "")
  if string.len(digits) == 11 and string.sub(digits, 1, 1) == "8" then
    digits = "7" .. string.sub(digits, 2)
  end
  if digits ~= "" and seen[digits] == nil then
    item.normalizedPhone = digits
    table.insert(result, item)
    seen[digits] = true
  end
end
return result""",
        "expected_runtime_followup": [
            {"id": 1, "name": "A", "phone": "8 (999) 123-45-67", "normalizedPhone": "79991234567"},
            {"id": 4, "name": "D", "phone": "8-921-000-11-22", "normalizedPhone": "79210001122"},
        ],
    },
    {
        "id": "pack2_fallback_target_id",
        "context": {
            "wf": {
                "vars": {"request": {"externalId": "", "crmId": "CRM-77"}},
                "initVariables": {"requestId": "REQ-500"},
            }
        },
        "prompts": {
            "ru": """Определи значение targetId.
Если request.externalId заполнен, верни его.
Если нет, но заполнен request.crmId, верни его.
Иначе верни initVariables.requestId.
Верни результат в targetId.""",
            "en": """Determine targetId.
If request.externalId is present, return it.
Otherwise, if request.crmId is present, return it.
Otherwise return initVariables.requestId.
Return the result as targetId.""",
            "noisy": """В интеграции с несколькими системами идентификатор заявки может приходить из разных источников.
Для следующего шага нам нужен единый идентификатор без дополнительной логики в low-code узлах.
Определи значение targetId: если request.externalId заполнен, используй его; если нет, но есть request.crmId, используй его; иначе верни initVariables.requestId.
Верни результат в targetId.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "targetId",
        "expected_lua_initial": """local externalId = wf.vars.request.externalId
if externalId ~= nil and externalId ~= "" then
  return externalId
end
local crmId = wf.vars.request.crmId
if crmId ~= nil and crmId ~= "" then
  return crmId
end
return wf.initVariables.requestId""",
        "expected_runtime_initial": "CRM-77",
        "followup_user": "Нет, верни только raw Lua без JSON и без оберток. Логику не меняй.",
        "expected_mode_followup": "raw_lua",
        "expected_output_key_followup": None,
        "expected_lua_followup": """local externalId = wf.vars.request.externalId
if externalId ~= nil and externalId ~= "" then
  return externalId
end
local crmId = wf.vars.request.crmId
if crmId ~= nil and crmId ~= "" then
  return crmId
end
return wf.initVariables.requestId""",
        "expected_runtime_followup": "CRM-77",
    },
    {
        "id": "pack2_priority_approval_bucket",
        "context": {"wf": {"vars": {"amount": 150000, "region": "KZ", "vip": False, "productType": "integration"}}},
        "prompts": {
            "ru": """Определи approvalBucket.
Если vip = true, верни vip.
Если amount больше 100000 и region = MSK, верни senior_msk.
Если amount больше 100000 или productType = integration, верни senior_common.
Во всех остальных случаях верни standard.""",
            "en": """Determine approvalBucket.
If vip is true, return vip.
If amount is greater than 100000 and region is MSK, return senior_msk.
If amount is greater than 100000 or productType is integration, return senior_common.
Otherwise return standard.""",
            "noisy": """У нас несколько правил маршрутизации для согласования заявок, и бизнес просит пока не переносить их в отдельный сервис правил.
На данном этапе достаточно вычислить один технический бакет для следующего маршрута.
Определи approvalBucket: если vip = true, верни vip; если amount > 100000 и region = MSK, верни senior_msk; если amount > 100000 или productType = integration, верни senior_common; иначе standard.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "approvalBucket",
        "expected_lua_initial": """local amount = tonumber(wf.vars.amount) or 0
local region = wf.vars.region
local vip = wf.vars.vip
local productType = wf.vars.productType
if vip == true then
  return "vip"
end
if amount > 100000 and region == "MSK" then
  return "senior_msk"
end
if amount > 100000 or productType == "integration" then
  return "senior_common"
end
return "standard\"""".replace('\\"', '"'),
        "expected_runtime_initial": "senior_common",
        "followup_user": "Нужен другой ключ: routeBucket. Логику не меняй.",
        "expected_mode_followup": "json_with_lua_wrappers",
        "expected_output_key_followup": "routeBucket",
        "expected_lua_followup": """local amount = tonumber(wf.vars.amount) or 0
local region = wf.vars.region
local vip = wf.vars.vip
local productType = wf.vars.productType
if vip == true then
  return "vip"
end
if amount > 100000 and region == "MSK" then
  return "senior_msk"
end
if amount > 100000 or productType == "integration" then
  return "senior_common"
end
return "standard\"""".replace('\\"', '"'),
        "expected_runtime_followup": "senior_common",
    },
    {
        "id": "pack2_flatten_package_rows",
        "context": {
            "wf": {
                "vars": {
                    "packages": [
                        {"packageId": "P1", "items": [{"sku": "A", "qty": "2"}, {"sku": "B", "qty": "1"}]},
                        {"packageId": "P2", "items": {"sku": "C", "qty": "5"}},
                    ]
                }
            }
        },
        "prompts": {
            "ru": """Преобразуй packages в плоский массив строк packageRows.
Для каждого item создай объект с полями packageId, sku, qty.
Если items внутри package не массив, а один объект, сначала приведи его к массиву.""",
            "en": """Transform packages into a flat array named packageRows.
For each item create an object with packageId, sku, and qty.
If items inside a package is a single object instead of an array, normalize it to an array first.""",
            "noisy": """Нам нужно подготовить данные для следующего шага выгрузки в табличный формат, поэтому вложенная структура packages сейчас неудобна.
Ожидается плоский массив строк, где каждая строка соответствует одной позиции из package.
Преобразуй packages в packageRows, а если items внутри package не массив, а один объект, сначала приведи его к массиву.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "packageRows",
        "expected_lua_initial": """local result = _utils.array.new()
for _, pkg in ipairs(wf.vars.packages) do
  local items = pkg.items
  if type(items) ~= "table" then
    items = {items}
  else
    local isArray = true
    for k, v in pairs(items) do
      if type(k) ~= "number" or math.floor(k) ~= k then
        isArray = false
        break
      end
    end
    if not isArray then
      items = {items}
    end
  end
  for _, item in ipairs(items) do
    table.insert(result, {packageId = pkg.packageId, sku = item.sku, qty = item.qty})
  end
end
return result""",
        "expected_runtime_initial": [
            {"packageId": "P1", "sku": "A", "qty": "2"},
            {"packageId": "P1", "sku": "B", "qty": "1"},
            {"packageId": "P2", "sku": "C", "qty": "5"},
        ],
        "followup_user": "Верни только raw Lua без JSON и без пояснений. Логику не меняй.",
        "expected_mode_followup": "raw_lua",
        "expected_output_key_followup": None,
        "expected_lua_followup": """local result = _utils.array.new()
for _, pkg in ipairs(wf.vars.packages) do
  local items = pkg.items
  if type(items) ~= "table" then
    items = {items}
  else
    local isArray = true
    for k, v in pairs(items) do
      if type(k) ~= "number" or math.floor(k) ~= k then
        isArray = false
        break
      end
    end
    if not isArray then
      items = {items}
    end
  end
  for _, item in ipairs(items) do
    table.insert(result, {packageId = pkg.packageId, sku = item.sku, qty = item.qty})
  end
end
return result""",
        "expected_runtime_followup": [
            {"packageId": "P1", "sku": "A", "qty": "2"},
            {"packageId": "P1", "sku": "B", "qty": "1"},
            {"packageId": "P2", "sku": "C", "qty": "5"},
        ],
    },
    {
        "id": "pack2_sla_breach_flag",
        "context": {"wf": {"vars": {"ticket": {"createdTs": 1710000000, "priority": "high"}}, "initVariables": {"nowTs": 1710005401}}},
        "prompts": {
            "ru": """Определи флаг slaBreached.
Если priority = high, используй порог 3600 секунд.
Во всех остальных случаях используй порог 14400 секунд.
Сравни nowTs из initVariables и ticket.createdTs.
Если прошло больше порога, верни true, иначе false.""",
            "en": """Determine the slaBreached flag.
If priority is high, use a threshold of 3600 seconds.
Otherwise use a threshold of 14400 seconds.
Compare nowTs from initVariables with ticket.createdTs.
If the elapsed time is greater than the threshold, return true, otherwise false.""",
            "noisy": """Для мониторинга инцидентов нам нужен простой технический флаг, который подскажет, ушел ли тикет за пределы SLA до следующего шага маршрутизации.
Пока не нужно ничего писать в историю и не нужно считать сложные календари — достаточно простого сравнения timestamp.
Определи slaBreached: если priority = high, порог 3600 секунд, иначе 14400 секунд; сравни initVariables.nowTs и ticket.createdTs; если прошло больше порога, верни true, иначе false.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "slaBreached",
        "expected_lua_initial": """local createdTs = tonumber(wf.vars.ticket.createdTs) or 0
local nowTs = tonumber(wf.initVariables.nowTs) or 0
local priority = wf.vars.ticket.priority
local threshold = 14400
if priority == "high" then
  threshold = 3600
end
return (nowTs - createdTs) > threshold""",
        "expected_runtime_initial": True,
        "followup_user": "Нужен другой ключ: escalationFlag. Логику не меняй.",
        "expected_mode_followup": "json_with_lua_wrappers",
        "expected_output_key_followup": "escalationFlag",
        "expected_lua_followup": """local createdTs = tonumber(wf.vars.ticket.createdTs) or 0
local nowTs = tonumber(wf.initVariables.nowTs) or 0
local priority = wf.vars.ticket.priority
local threshold = 14400
if priority == "high" then
  threshold = 3600
end
return (nowTs - createdTs) > threshold""",
        "expected_runtime_followup": True,
    },
    {
        "id": "pack2_assignee_queue",
        "context": {"wf": {"vars": {"country": "UZ", "source": "website", "vip": False}}},
        "prompts": {
            "ru": """Определи assigneeQueue.
Если vip = true, верни vip_queue.
Если country не равен RU, верни international_queue.
Если source = partner, верни partner_queue.
Во всех остальных случаях верни default_queue.""",
            "en": """Determine assigneeQueue.
If vip is true, return vip_queue.
If country is not RU, return international_queue.
If source is partner, return partner_queue.
Otherwise return default_queue.""",
            "noisy": """В процессе распределения входящих обращений нам нужен один служебный маршрут, который будет использован следующим low-code узлом.
Сейчас важны только три простых правила приоритета без дополнительных справочников.
Определи assigneeQueue: если vip = true, верни vip_queue; если country не равен RU, верни international_queue; если source = partner, верни partner_queue; иначе default_queue.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "assigneeQueue",
        "expected_lua_initial": """if wf.vars.vip == true then
  return "vip_queue"
end
if wf.vars.country ~= "RU" then
  return "international_queue"
end
if wf.vars.source == "partner" then
  return "partner_queue"
end
return "default_queue\"""".replace('\\"', '"'),
        "expected_runtime_initial": "international_queue",
        "followup_user": "Верни только raw Lua без JSON. Логику не меняй.",
        "expected_mode_followup": "raw_lua",
        "expected_output_key_followup": None,
        "expected_lua_followup": """if wf.vars.vip == true then
  return "vip_queue"
end
if wf.vars.country ~= "RU" then
  return "international_queue"
end
if wf.vars.source == "partner" then
  return "partner_queue"
end
return "default_queue\"""".replace('\\"', '"'),
        "expected_runtime_followup": "international_queue",
    },
    {
        "id": "pack2_customer_display_name",
        "context": {
            "wf": {
                "vars": {
                    "customer": {
                        "companyName": "",
                        "firstName": "Ivan",
                        "lastName": "Petrov",
                        "email": "user@example.com",
                    }
                }
            }
        },
        "prompts": {
            "ru": """Собери customerDisplayName.
Если companyName заполнен, верни его.
Иначе, если есть firstName или lastName, верни строку из lastName и firstName через пробел.
Если и их нет, верни email.
Если нет ничего, верни Unknown.""",
            "en": """Build customerDisplayName.
If companyName is present, return it.
Otherwise, if firstName or lastName exists, return lastName and firstName separated by a space.
If they are both missing, return email.
If nothing is available, return Unknown.""",
            "noisy": """В разных источниках карточка клиента может быть как по физическому лицу, так и по компании, поэтому в интерфейсе нужен единый display name.
Сейчас нам не нужна идеальная форматизация, только устойчивый fallback для дальнейших шагов процесса.
Собери customerDisplayName: если companyName заполнен, верни его; иначе, если есть firstName или lastName, собери строку из lastName и firstName через пробел; если и их нет, верни email; если нет ничего, верни Unknown.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "customerDisplayName",
        "expected_lua_initial": """local customer = wf.vars.customer
local companyName = tostring(customer.companyName or "")
if companyName ~= "" then
  return companyName
end
local firstName = tostring(customer.firstName or "")
local lastName = tostring(customer.lastName or "")
local fullName = ""
if lastName ~= "" and firstName ~= "" then
  fullName = lastName .. " " .. firstName
elseif lastName ~= "" then
  fullName = lastName
elseif firstName ~= "" then
  fullName = firstName
end
if fullName ~= "" then
  return fullName
end
local email = tostring(customer.email or "")
if email ~= "" then
  return email
end
return "Unknown\"""".replace('\\"', '"'),
        "expected_runtime_initial": "Petrov Ivan",
        "followup_user": "Нужен другой ключ: displayName. Логику не меняй.",
        "expected_mode_followup": "json_with_lua_wrappers",
        "expected_output_key_followup": "displayName",
        "expected_lua_followup": """local customer = wf.vars.customer
local companyName = tostring(customer.companyName or "")
if companyName ~= "" then
  return companyName
end
local firstName = tostring(customer.firstName or "")
local lastName = tostring(customer.lastName or "")
local fullName = ""
if lastName ~= "" and firstName ~= "" then
  fullName = lastName .. " " .. firstName
elseif lastName ~= "" then
  fullName = lastName
elseif firstName ~= "" then
  fullName = firstName
end
if fullName ~= "" then
  return fullName
end
local email = tostring(customer.email or "")
if email ~= "" then
  return email
end
return "Unknown\"""".replace('\\"', '"'),
        "expected_runtime_followup": "Petrov Ivan",
    },
    {
        "id": "pack2_order_validation_split",
        "context": {
            "wf": {
                "vars": {
                    "orders": [
                        {"id": "O1", "amount": 100, "customerId": "C1"},
                        {"id": "O2", "amount": 0, "customerId": "C2"},
                        {"id": "O3", "amount": 500, "customerId": ""},
                        {"id": "O4", "amount": 10, "customerId": "C4"},
                    ]
                }
            }
        },
        "prompts": {
            "ru": """Проверь массив orders и верни объект validationResult с двумя массивами: validOrders и invalidOrders.
Заказ считается валидным, если amount > 0 и customerId заполнен.
Во всех остальных случаях заказ должен попасть в invalidOrders.""",
            "en": """Validate the orders array and return a validationResult object with two arrays: validOrders and invalidOrders.
An order is valid if amount > 0 and customerId is present.
Otherwise the order must go to invalidOrders.""",
            "noisy": """Перед отправкой заказов в следующий интеграционный шаг нам нужно быстро разделить их на пригодные и проблемные, чтобы не падать всем пакетом целиком.
На этом этапе достаточно простой технической валидации без справочников и внешних запросов.
Проверь массив orders и верни validationResult с массивами validOrders и invalidOrders.
Заказ валиден, если amount > 0 и customerId заполнен; иначе он должен попасть в invalidOrders.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "validationResult",
        "expected_lua_initial": """local validOrders = _utils.array.new()
local invalidOrders = _utils.array.new()
for _, order in ipairs(wf.vars.orders) do
  local amount = tonumber(order.amount) or 0
  local customerId = tostring(order.customerId or "")
  if amount > 0 and customerId ~= "" then
    table.insert(validOrders, order)
  else
    table.insert(invalidOrders, order)
  end
end
return {
  validOrders = validOrders,
  invalidOrders = invalidOrders
}""",
        "expected_runtime_initial": {
            "validOrders": [
                {"id": "O1", "amount": 100, "customerId": "C1"},
                {"id": "O4", "amount": 10, "customerId": "C4"},
            ],
            "invalidOrders": [
                {"id": "O2", "amount": 0, "customerId": "C2"},
                {"id": "O3", "amount": 500, "customerId": ""},
            ],
        },
        "followup_user": "Верни только raw Lua. Логику и структуру результата не меняй.",
        "expected_mode_followup": "raw_lua",
        "expected_output_key_followup": None,
        "expected_lua_followup": """local validOrders = _utils.array.new()
local invalidOrders = _utils.array.new()
for _, order in ipairs(wf.vars.orders) do
  local amount = tonumber(order.amount) or 0
  local customerId = tostring(order.customerId or "")
  if amount > 0 and customerId ~= "" then
    table.insert(validOrders, order)
  else
    table.insert(invalidOrders, order)
  end
end
return {
  validOrders = validOrders,
  invalidOrders = invalidOrders
}""",
        "expected_runtime_followup": {
            "validOrders": [
                {"id": "O1", "amount": 100, "customerId": "C1"},
                {"id": "O4", "amount": 10, "customerId": "C4"},
            ],
            "invalidOrders": [
                {"id": "O2", "amount": 0, "customerId": "C2"},
                {"id": "O3", "amount": 500, "customerId": ""},
            ],
        },
    },
    {
        "id": "pack2_notification_payload",
        "context": {
            "wf": {
                "vars": {
                    "request": {
                        "id": "INC-12",
                        "priority": "high",
                        "subject": "VPN access",
                        "requesterEmail": "",
                        "requesterTelegram": "@alex",
                    }
                }
            }
        },
        "prompts": {
            "ru": """Собери notificationPayload как объект с полями title, body и channel.
title должен быть в формате Request <id>.
body должен быть в формате Priority: <priority>. Subject: <subject>.
Если requesterEmail заполнен, channel = email.
Иначе, если requesterTelegram заполнен, channel = telegram.
Иначе channel = internal.""",
            "en": """Build notificationPayload as an object with title, body, and channel.
title must be in the format Request <id>.
body must be in the format Priority: <priority>. Subject: <subject>.
If requesterEmail is present, channel = email.
Otherwise, if requesterTelegram is present, channel = telegram.
Otherwise channel = internal.""",
            "noisy": """Нам нужно подготовить единый payload для следующего узла уведомлений, чтобы тот не думал о форматировании.
Внутри достаточно только канала и двух текстовых полей, без внешних шаблонов и без дополнительной логики.
Собери notificationPayload как объект с полями title, body и channel: title = Request <id>, body = Priority: <priority>. Subject: <subject>.
Если requesterEmail заполнен, channel = email; иначе, если requesterTelegram заполнен, channel = telegram; иначе internal.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "notificationPayload",
        "expected_lua_initial": """local request = wf.vars.request
local channel = "internal"
local requesterEmail = tostring(request.requesterEmail or "")
local requesterTelegram = tostring(request.requesterTelegram or "")
if requesterEmail ~= "" then
  channel = "email"
elseif requesterTelegram ~= "" then
  channel = "telegram"
end
return {
  title = "Request " .. tostring(request.id or ""),
  body = "Priority: " .. tostring(request.priority or "") .. ". Subject: " .. tostring(request.subject or "") .. ".",
  channel = channel
}""",
        "expected_runtime_initial": {
            "title": "Request INC-12",
            "body": "Priority: high. Subject: VPN access.",
            "channel": "telegram",
        },
        "followup_user": "Нужен другой ключ: messagePayload. Логику не меняй.",
        "expected_mode_followup": "json_with_lua_wrappers",
        "expected_output_key_followup": "messagePayload",
        "expected_lua_followup": """local request = wf.vars.request
local channel = "internal"
local requesterEmail = tostring(request.requesterEmail or "")
local requesterTelegram = tostring(request.requesterTelegram or "")
if requesterEmail ~= "" then
  channel = "email"
elseif requesterTelegram ~= "" then
  channel = "telegram"
end
return {
  title = "Request " .. tostring(request.id or ""),
  body = "Priority: " .. tostring(request.priority or "") .. ". Subject: " .. tostring(request.subject or "") .. ".",
  channel = channel
}""",
        "expected_runtime_followup": {
            "title": "Request INC-12",
            "body": "Priority: high. Subject: VPN access.",
            "channel": "telegram",
        },
    },
    {
        "id": "pack2_aggregate_sku_totals",
        "context": {
            "wf": {
                "vars": {
                    "packages": [
                        {"packageId": "P1", "items": [{"sku": "A", "qty": "2"}, {"sku": "B", "qty": "1"}]},
                        {"packageId": "P2", "items": {"sku": "A", "qty": "3"}},
                    ]
                }
            }
        },
        "prompts": {
            "ru": """Посчитай суммарное количество по каждому sku во всех packages и верни массив skuTotals.
Каждый элемент массива должен иметь поля sku и totalQty.
Если items внутри package не массив, а один объект, сначала приведи его к массиву.
Отсортируй итоговый массив по sku по возрастанию.""",
            "en": """Calculate total quantity for each sku across all packages and return an array skuTotals.
Each element of the array must have sku and totalQty.
If items inside a package is a single object instead of an array, normalize it to an array first.
Sort the final array by sku ascending.""",
            "noisy": """Для следующего шага аналитики нам нужен простой агрегат по всем позициям заказа без обращения к внешним сервисам.
Структура packages местами нестабильна, потому что items может приходить и массивом, и одиночным объектом.
Посчитай суммарное количество по каждому sku во всех packages и верни массив skuTotals с полями sku и totalQty, отсортированный по sku по возрастанию.""",
        },
        "expected_mode_initial": "json_with_lua_wrappers",
        "expected_output_key_initial": "skuTotals",
        "expected_lua_initial": """local sums = {}
for _, pkg in ipairs(wf.vars.packages) do
  local items = pkg.items
  if type(items) ~= "table" then
    items = {items}
  else
    local isArray = true
    for k, v in pairs(items) do
      if type(k) ~= "number" or math.floor(k) ~= k then
        isArray = false
        break
      end
    end
    if not isArray then
      items = {items}
    end
  end
  for _, item in ipairs(items) do
    local sku = item.sku
    local qty = tonumber(item.qty) or 0
    if sums[sku] == nil then
      sums[sku] = 0
    end
    sums[sku] = sums[sku] + qty
  end
end
local keys = {}
for sku, _ in pairs(sums) do
  table.insert(keys, sku)
end
table.sort(keys)
local result = _utils.array.new()
for _, sku in ipairs(keys) do
  table.insert(result, {sku = sku, totalQty = sums[sku]})
end
return result""",
        "expected_runtime_initial": [{"sku": "A", "totalQty": 5}, {"sku": "B", "totalQty": 1}],
        "followup_user": "Верни только raw Lua, без JSON и без пояснений. Логику не меняй.",
        "expected_mode_followup": "raw_lua",
        "expected_output_key_followup": None,
        "expected_lua_followup": """local sums = {}
for _, pkg in ipairs(wf.vars.packages) do
  local items = pkg.items
  if type(items) ~= "table" then
    items = {items}
  else
    local isArray = true
    for k, v in pairs(items) do
      if type(k) ~= "number" or math.floor(k) ~= k then
        isArray = false
        break
      end
    end
    if not isArray then
      items = {items}
    end
  end
  for _, item in ipairs(items) do
    local sku = item.sku
    local qty = tonumber(item.qty) or 0
    if sums[sku] == nil then
      sums[sku] = 0
    end
    sums[sku] = sums[sku] + qty
  end
end
local keys = {}
for sku, _ in pairs(sums) do
  table.insert(keys, sku)
end
table.sort(keys)
local result = _utils.array.new()
for _, sku in ipairs(keys) do
  table.insert(result, {sku = sku, totalQty = sums[sku]})
end
return result""",
        "expected_runtime_followup": [{"sku": "A", "totalQty": 5}, {"sku": "B", "totalQty": 1}],
    },
]

