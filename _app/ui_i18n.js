/* Local RU/EN interface dictionary. Business values are never sent for translation.
   Text-node updates preserve event handlers, entered values and DOM identity. */
(() => {
  'use strict';
  const dictionary = {
    'Ткацкий цех':'Weaving MES','Производство':'Production','Скрыть меню':'Hide menu','Открыть меню':'Show menu',
    'Разделы':'Sections','Сейчас в цеху':'Shop floor','Дашборд':'Dashboard','Тикеты':'Tickets',
    'Доска цеха':'Shop floor board',
    'Оператор не найден':'Operator not found',
    'Обход цеха':'Shop floor walk','Смена':'Shift','Заправка':'Machine setup','Расстановка':'Shift assignments',
    'Планирование':'Planning','План':'Plan','Отчёты':'Reports','Производственный отчёт':'Production report',
    'Простои':'Downtime','История станков':'Machine history','Ручные остановы':'Manual stops',
    'Зарплата':'Payroll','Справочники':'Directories','Операторы':'Operators','Настройки':'Settings',
    'Пользователи':'Users','Язык интерфейса':'Interface language','Русский':'Русский',
    'Нет доступных разделов. Обратитесь к администратору.':'No sections available. Contact your administrator.',
    'Вход в систему цеха':'Sign in to MES','Логин':'Username','Пароль':'Password','Новый пароль':'New password',
    'Временный пароль нужно сменить':'Change your temporary password','Войти':'Sign in','Выйти':'Sign out',
    'Новый пользователь':'New user','Имя':'Name','Роль':'Role','Временный пароль':'Temporary password',
    'Настройка доступа':'Access settings','Индивидуально':'Custom access','По шаблону роли':'Role defaults',
    'Создать':'Create','Отмена':'Cancel','Что пользователь видит':'Sections the user can see',
    'Что пользователь может менять':'Actions the user can perform','Доступ':'Access','Активен':'Active',
    'Последний вход':'Last sign-in','Администратор':'Administrator','Мастер':'Supervisor','Оператор':'Operator',
    'Наблюдатель':'Viewer','Администратор: полный доступ.':'Administrator: full access.',
    'Для просмотра оставьте действия выключенными.':'Leave actions unchecked for read-only access.',
    'Изменить доступ':'Edit access','Отключить':'Disable','Включить':'Enable','Да':'Yes','Нет':'No','да':'yes','нет':'no',
    'Выберите хотя бы один раздел':'Select at least one section','Нужны логин и временный пароль':'Username and temporary password are required',
    'Права пользователя сохранены':'User access saved','Неверный логин или пароль':'Invalid username or password',
    'Сначала выберите доступные разделы, затем разрешённые действия. Просмотр раздела не разрешает менять его данные.':'Choose visible sections, then permitted actions. Viewing a section does not allow changes.',
    'Администратор управляет пользователями и имеет полный доступ. Индивидуальные ограничения проверяются сервером при каждом запросе.':'Administrators manage users and have full access. The server checks custom permissions on every request.',
    'День':'Day','Только таблица, на весь экран. Выход — Esc':'Full-screen table. Press Esc to exit',
    'Развернуть отчёт':'Expand report','Скачать Excel':'Download Excel','Показывать':'Show',
    'все станки':'all machines','только с красным':'red flags only','с жёлтым или красным':'amber or red flags',
    'Сбросить фильтры и сортировку':'Reset filters and sorting','Раскрыть колонки':'Expand columns',
    'Свёрнутая смена показывает только итог':'A collapsed shift shows totals only','Смены A / B / C':'Shifts A / B / C',
    'Свернуть':'Collapse','Заправка станка':'Machine setup','С какого дня':'Effective from',
    'Вес штуки, кг':'Unit weight, kg','0,635 или 635 г':'0.635 or 635 g','PPT, пиков на изделие':'PPT, picks per product',
    'Панелей':'Panels','Пряжа':'Yarn','Лот':'Lot','Сохранить':'Save','Заправка с дня':'Setup effective from',
    'Ворс:':'Pile:','Грунт':'Ground','Панели':'Panels','Вес шт, кг':'Unit weight, kg','100% кг':'100% kg',
    'Норма 1С, %':'1C target, %','Ворс · лот':'Pile · lot','Грунт · лот':'Ground · lot','Уток · лот':'Weft · lot',
    'Кромка · лот':'Selvage · lot','Бордюр · лот':'Border · lot','Ворс (Pile)':'Pile warp',
    'Уток (Weft)':'Weft','Основа (Ground)':'Ground warp','Прочие':'Other','Mending time, сек':'Mending time, sec',
    'Станки':'Machines','Сохранить изменения':'Save changes','Значение — на отмеченные':'Apply value to selected',
    'Строку — на отмеченные':'Apply row to selected','Отметить с тем же кодом ткани':'Select matching cloth code',
    'Отменить правки':'Discard changes','Как в Excel:':'Like Excel:','— вниз по колонке,':'— down the column,',
    '— взять значение сверху, блок из Excel вставляется целиком (':'— copy the value above; paste an Excel range (',
    'Справочник пряжи':'Yarn directory','Вид':'Type','ворс':'pile','грунт':'ground','уток':'weft',
    'Добавить':'Add','Загрузить из 1С (.mxl)':'Import from 1C (.mxl)','На станках':'Machine overview',
    'весь день':'whole day','Показать':'Show','Для монитора':'Wall display','Карточки станков':'Machine cards',
    'только стоящие':'stopped only','только с тикетом':'with tickets only','Что заправлено':'Current setup',
    'Наработка':'Output','Обрывы':'Breaks','Станок':'Machine','Состояние':'State','Тикет':'Ticket',
    'Об/мин':'RPM','Дизайн':'Design','Размер':'Size','Плотн.':'GSM','Тыс. пиков':'Thousand picks','Метры':'Metres',
    'Полотенец':'Towels','КПД':'Time efficiency','Уток':'Weft','Основа':'Ground warp','Ворс':'Pile warp','Ручные':'Manual',
    'Разделы плана':'Plan sections','По станкам':'Machine schedule','Заказы и сроки':'Orders and due dates',
    'Сверка PPT':'PPT reconciliation','Обмен с 1С':'1C integration','Коды ткани':'Cloth codes',
    'Период с':'From','По':'To','Навигация по датам':'Date navigation',
    'Сдвинуть показанный период на неделю назад':'Previous week','← 7 дней':'← 7 days','Сегодня':'Today',
    'Сдвинуть показанный период на неделю вперёд':'Next week','7 дней →':'7 days →','Назначить на дней':'Schedule for days',
    'без воскресений':'skip Sundays','Редактировать':'Edit','Отменить правку':'Undo edit','Загрузить план из Excel':'Import Excel plan',
    'Заказы':'Orders','Поиск: заказ, дизайн, клиент':'Search: order, design, customer','Поиск заказа':'Search orders',
    'Все':'All','Из 1С':'From 1C','Нет в 1С':'Missing from 1C','Не хватает':'Shortfall','Не в плане':'Unscheduled',
    'Выберите ячейку станка для редактирования.':'Select a machine cell to edit.',
    'Выбран заказ:':'Selected order:','Выбран':'Selected','Уточните изделие':'Select the product',
    'Синяя рамка — выбранные ячейки · голубой фон — выбранный заказ · ! — уточните изделие':'Blue border: selected cells · light blue: selected order · !: select the product',
    'Цвет — заказ · серый день — воскресенье · пунктир — уточните изделие':'Colour: order · grey day: Sunday · dashed border: select product',
    'Как назначать заказы и читать план / факт':'How to schedule orders and read planned / actual output',
    'Заказ':'Order','Изделие заказа':'Order product','Пометка':'Note','Praborka 35 sm, рулон…':'Drawing-in 35 cm, roll…',
    'Очистить клетку':'Clear cell','Изделие':'Product','PPT 1С':'1C PPT','По счётчикам':'From counters',
    'Разница':'Difference','Сек/ряд 1С':'1C seconds / row','Норма 1С':'1C target','Дней':'Days','Вывод':'Result',
    'По станкам и дням':'By machine and day','Рядов':'Rows','Код на станке':'Machine code','Когда':'When',
    'Кто':'Who','Действие':'Action','Итог':'Result','Закрыть':'Close','Срок':'Due date',
    'Поставить в план':'Schedule order','Взять заказы из 1С':'Import 1C orders','Показать закрытые':'Show closed orders',
    'Скрыть закрытые':'Hide closed orders','Сделано':'Completed','Готовность':'Progress','Темп в сутки':'Daily rate',
    'Осталось дней':'Days remaining','Прогноз':'Forecast','Пики на изделие':'Picks per product',
    'Артикул 1С или код ткани':'1C item or cloth code','Пиков на изделие':'Picks per product',
    'Коды ткани на станках, которые не опознаны как артикул 1С':'Machine cloth codes without a matching 1C item',
    'Рядов за 2 недели':'Rows in 2 weeks','Последний день':'Latest day','Артикул 1С':'1C item',
    'Связанные коды':'Linked codes','Кто связал':'Linked by','Посчитать':'Calculate',
    'Повторить расстановку прошлой смены':'Copy previous shift assignments','Код':'Code','Станков':'Machines',
    'Зарплата, сум':'Pay, UZS','Уток /cmpx':'Weft / 100k picks','Основа /cmpx':'Warp / 100k picks',
    'Ожидание, мин':'Waiting, min','Выработка по станкам':'Output by machine','Артикул':'Item',
    'К начислению, сум':'Payable, UZS','Основа и ворс':'Ground and pile warp','Утвердить':'Approve','Печать':'Print',
    'Оператор для отмеченных станков':'Operator for selected machines','Назначить':'Assign',
    'Как в прошлую такую смену':'Copy previous matching shift','Из FACT':'From FACT','Отметить все станки':'Select all machines',
    'Мастер смены':'Shift supervisor','Мастерица смены':'Shift lead','Мастерицы смены':'Shift leads','Примечание':'Comment',
    'Код или имя оператора':'Operator code or name','Введите код или имя':'Enter code or name',
    'Выберите оператора из списка':'Select an operator from the list','— выберите оператора —':'— select an operator —',
    'Документы за неделю':'Weekly shift records','Смена A':'Shift A','Смена B':'Shift B','Смена C':'Shift C',
    'оператор':'operator','мастерица':'shift lead','мастер':'supervisor','Взять имена из FACT':'Import names from FACT',
    'Загрузить список из другой системы или Excel':'Import a list from another system or Excel',
    'Загрузить':'Import','С':'From','Кого':'People','операторы':'operators','мастерицы':'shift leads','Смен':'Shifts',
    'Ожидание за смену, мин':'Waiting per shift, min','Ручных за смену':'Manual stops per shift','Смены':'Shifts',
    'Группа':'Group','все':'all','махровые D':'D terry looms','жаккард J':'J jacquard looms',
    'Ручных':'Manual stops','Ручные, ч':'Manual stops, h','Ожидание, ч':'Waiting, h','Главная потеря':'Main loss',
    'мин':'min','Простой, мин':'Downtime, min','Дата в цехе':'Shop floor date','Период':'Period',
    'Сутки · 00–24':'Day · 00–24','Смена A · 07–15':'Shift A · 07–15','Смена B · 15–23':'Shift B · 15–23',
    'Смена C · 23–07 (+1 день)':'Shift C · 23–07 (+1 day)','Все станки':'All machines','Масштаб':'Zoom','Обзор':'Overview',
    'Ручной останов':'Manual stop','Другие остановы':'Other stops','Работа · расчёт':'Running · estimated',
    'Нет подтверждённого состояния':'State not confirmed','Тикет · нижняя дорожка':'Ticket · lower track',
    'Время ещё не наступило':'Future time','Причина':'Reason','Остановов':'Stops','Потеряно, мин':'Lost time, min',
    'Доля':'Share','MTTR, сек':'MTTR, sec','Реакция, сек':'Response, sec',
    'Станки: где теряем больше всего':'Machines with the largest losses','Уток /100k':'Weft / 100k',
    'Основа и ворс /100k':'Ground and pile warp / 100k','Ручные, мин':'Manual stops, min','Реакция 90 %':'90th percentile response',
    'Операторы: как быстро подходят к станку':'Operator response time','Строка':'Group by','день':'day','смена':'shift',
    'станок':'machine','Монитор в цехе':'Shop floor display','Открыть доску':'Open board','открытые':'open',
    'Обновить':'Refresh','Начало':'Start','Простой':'Downtime','Сигнал станка':'Machine signal',
    'Причина в отчёте':'Reported reason','Откуда':'Source','Категория':'Category','Ставка, сум':'Rate, UZS',
    'За что':'Rate basis','за 1000 пиков':'per 1,000 picks','за один пик':'per pick',
    'Андон: станок стоит без тикета':'Andon: stopped machine without a ticket','«Нет тикета» через, мин':'No-ticket warning after, min',
    'Тревога на доске через, мин':'Board alarm after, min','Мастеру в телеграм через, мин':'Notify supervisor after, min',
    'Ключи API для 1С и других программ':'API keys for 1C and other applications','Для кого':'Client',
    '1С, бот, BI':'1C, bot, BI','Права':'Permissions','читать':'read','присылать заказы':'submit orders',
    'тикеты':'tickets','Выдать ключ':'Create key','Описание API':'API documentation',
    'Начало ключа':'Key prefix','Выдан':'Issued','Последний запрос':'Last request',
    'Работает':'Running','Стоит':'Stopped','С тикетом':'With ticket','Обрывы утка':'Weft breaks',
    'Обрывы основы':'Ground warp breaks','Обрывы ворса':'Pile warp breaks','Заказов в работе':'Active orders',
    'Полотенец в плане':'Planned towels','Отстаём':'Behind schedule','Осталось':'Remaining','Не назначен':'Unassigned',
    'не задано':'not set','— не задано —':'— not set —','— не назначен —':'— unassigned —',
    'нет данных':'no data','Нет данных':'No data','Удалить':'Delete','Отозвать':'Revoke','Открыть':'Open',
    'Открыть для правки':'Reopen for editing','утверждена':'approved','черновик':'draft',
    'норма':'target','совпадает':'matches','проверьте PPT в 1С':'check PPT in 1C','план':'plan','факт':'actual',
    'Выберите изделие':'Select product','подобрать по размеру и GSM':'match size and GSM',
    'В заказе несколько изделий — выберите, какое ставить на станок.':'This order has several products. Select one for the machine.',
    'Сохранено':'Saved','Отменено':'Undone','Удалено':'Deleted','Закрыть сообщение':'Dismiss message',
    'Доступен только просмотр плана':'You have read-only access to the plan','нет прав':'Access denied',
    'нет доступа к разделу':'Access to this section is denied','нужно войти':'Please sign in',
    'Наладка':'Setup','Электрическая проблема':'Electrical issue','Вызов электрика':'Call electrician','ТОиР':'Maintenance',
    'Причина не указана':'Reason not specified','Не определена':'Unknown','Неопределена':'Unknown',
    'Обесточен':'Power off','Конец навоя':'Beam exhausted','Съём ткани':'Cloth doffing','Починка ткани':'Cloth mending',
    'Нет продукции':'No product','Ложная кромка':'False selvage','Отказ станка':'Machine failure','Прочее':'Other',
    'сигнал станка':'machine signal','тикет':'ticket','Работа (расчёт)':'Running (estimated)','Неизвестно':'Unknown',
    'Окончание':'End','В выбранном периоде':'Within selected period','Сверка со сменными итогами Toyota':'Reconciliation with Toyota shift totals',
    'Работа по итогу, мин':'Shift running total, min','Простой по итогу, мин':'Shift downtime total, min',
    'По журналу, мин':'Event log, min','Расчёт работы':'Running estimate','Согласуется':'Reconciled',
    'Недостаточно подтверждений':'Insufficient evidence','Статус':'Status','Не закрыт':'Open','Закрыт':'Closed',
    'не закрыт':'open','← Предыдущие':'← Previous','Следующие →':'Next →',
    'Загружаю журнал Toyota…':'Loading Toyota history…','Выберите остановку в списке или на шкале.':'Select a stop from the list or timeline.',
    'Остановок за этот период в журнале нет.':'No stops recorded for this period.',
    'Тикетов за этот период нет.':'No tickets for this period.',
    'Источник: журнал остановов Toyota.':'Source: Toyota stop log.','Источник: журнал тикетов MES.':'Source: MES tickets.',
    'Время регистрации в MES. Причина относится к тикету; связь с конкретным событием Toyota не установлена.':'Times recorded by MES. A ticket reason is not automatically linked to a Toyota event.',
    'В журнале есть пересечения. В сумме простой учитывается один раз; исходные события сохранены.':'Events overlap. Total downtime counts overlapping time once; original events are preserved.',
    'В локальной базе пока нет истории станков.':'No machine history in the local database yet.',
    'Нет станко-дней, где в плане изделие с PPT из 1С.':'No machine-days with a scheduled product and 1C PPT.',
    'План пуст: перетащите заказы на станки или загрузите Excel TOYOTA - LOOM PLAN.':'The plan is empty. Drag orders to machines or import the TOYOTA - LOOM PLAN workbook.',
    'Оператор назначен':'Operator assigned','Нет заказов':'No orders','Ничего не найдено':'No matches',
    'пн':'Mon','вт':'Tue','ср':'Wed','чт':'Thu','пт':'Fri','сб':'Sat','вс':'Sun',
    'сегодня':'today','выходной':'day off','успеваем':'on schedule','не в плане':'unscheduled',
    'Свернуть заказ':'Collapse order','Развернуть заказ':'Expand order',
    'Отозвать ключ? Программа, которая им пользуется, перестанет получать данные.':'Revoke this key? Its client will no longer receive data.',
    'Есть несохранённые правки — выбросить их?':'Discard unsaved changes?',
    'Удалить из справочника?':'Delete from the directory?',
    'Заполнить расстановку по данным FACT? То, что на экране, заменится.':'Replace current assignments with FACT data?',
    'Взять расстановку из прошлой такой же смены? То, что на экране, заменится.':'Replace current assignments with the previous matching shift?'
  };
  // Long help text is matched by its stable opening, only on complete text nodes.
  const help = [
    ['Щелчок по названию колонки','Click a column heading to sort; click again to reverse, and a third time to reset. Column filter:'],
    ['; для станков','; for machines —'],
    ['. Итоги и плитки сверху','Totals reflect the filtered rows. Click a machine number to edit GSM, unit weight, PPT, yarn and lot. Manual values are underlined.'],
    ['Запись действует с указанного дня','The setup is effective from the selected day until replaced. Empty fields use the item directory and 1C technical card.'],
    ['плохо: КПД','Critical: efficiency 1–69; pile 41+; weft / ground warp 61+; other 21+; total 121+'],
    ['внимание: КПД','Warning: efficiency 70–79; pile 30–40; weft / ground warp 50–60; other 16–20; total 91–120'],
    ['об/мин 250','RPM 250–519'],['об/мин ниже','RPM below 500'],
    ['в верхнюю левую ячейку)','into the top-left cell). Select machines to fill a value or row. Grey italic: directory value; normal: manual; yellow: unsaved; red: yarn missing from directory.'],
    ['Из 1С: номенклатура вида','Export the YARN item directory from 1C as a tabular document (.mxl). Each entry contains yarn, type, lot and supplier for machine setup choices.'],
    ['Одна пряжа — одно написание','Use one spelling per yarn. Spacing and letter case variants are matched to the same directory entry. Renaming also updates existing setups.'],
    ['Зелёный — станок работает','Green: running; red: stopped. Product design and yarn come from the 1C technical card. The supervisor selects the item because 1C machine assignments may be ambiguous.'],
    ['Перетащите заказ из списка слева','Drag an order onto a machine cell for the selected number of days. Drag a cell to move it; Ctrl copies. Shift-click selects a range; Ctrl-click adds cells. Delete clears, Ctrl+C / Ctrl+V copies, Ctrl+Z undoes. Double-click edits an order or note. Changes record who made them and when.'],
    ['Под заказом в прошедшие дни','Past cells show daily Toyota output: towels = rows × panels. 1C target attainment uses rows × 1C seconds per row / shift time; the 1C norm already includes 75% efficiency. Red means below 90%. Without a 1C norm, time efficiency is shown, red below 60%. Product specifications come from the planned order; manual setup takes priority.'],
    ['PPT по счётчикам','Counter PPT = picks / rows for days with a scheduled 1C product and at least 50 woven rows. Differences above 5% are flagged. Repeated discrepancies over three matching-code days request a 1C check. PPT affects kilograms; towel count uses rows and panels.'],
    ['Каждое сообщение 1С хранится','The last 5,000 1C messages and MES responses are retained. Parsed technical cards contain product specifications, panels, yarn lots, quantities and due dates.'],
    ['Факт берётся со счётчиков станка','Actual output is calculated from machine counters: rows × panels since the planned assignment. Daily rate is the average of the machine’s last seven working days.'],
    ['Введённое здесь главнее техкарты','Manual values take priority over technical cards and counter estimates. Automatic weftPerOneRow from 1C replaces manual entry when available.'],
    ['Код ткани набирают на станке','Machine cloth codes are entered manually; 1C uses item codes. Link them once so MES can associate machine output with a 1C product.'],
    ['Пики станок даёт независимо','Machine picks are recorded with or without an assigned operator. Select an operator to assign the calculated pay.'],
    ['Документы на смены A, B и C','Shift A, B and C records are created each morning from the previous matching shift. The supervisor edits, saves and approves. Approved records must be reopened before editing.'],
    ['Выделите строки в таблице пользователей','Copy rows from another user table or Excel, preferably with headings. Employees match by personnel number, which must equal the FACT operator code. Existing records are updated; new records are added. Review roles after import.'],
    ['Отображаемое имя','Display name\tLast name\tFirst name\tMiddle name\tPersonnel number\tPosition'],
    ['«Уток /cmpx»','Weft / 100k and warp / 100k are breaks per 100,000 picks. Waiting is the stop time before an operator responds.'],
    ['Станки отсортированы по простою','Machines are sorted by downtime, with the most urgent first. Main loss is the largest cause of lost time in the shift.'],
    ['Время цеха: UTC+5.','Shop floor time: UTC+5. Click a machine or event for details. Short stops are also listed. Running time is estimated only for completed shifts reconciled with the log. Grey gaps are not counted as running. Tickets do not replace Toyota signals.'],
    ['Обрывность приведена к 100 тысячам','Break rates are per 100,000 picks. Red marks values 1.5 times worse than the shop median. Manual stop duration includes nights and days off; losses within scheduled shifts are in Manual stops.'],
    ['Shed Eff —','Shed Eff compares fleet running time with calendar time. Time Eff is running / (running + stopped). Tot. Stop represents long stops. Prod Eff adds these back to Time Eff. Unclassified stops need a ticket; power-off time is shown separately.'],
    ['Станок сам называет причину','Toyota identifies technical causes such as weft, ground warp, pile and selvage breaks. Tickets do not override these signals. For power-off, manual and other stops, a ticket supplies the operational reason.'],
    ['Зарплата оператора за смену','Shift pay = picks on the operator’s assigned machines × rate. Check the rate unit; a machine may produce about 220,000 picks per shift.'],
    ['Обрыв, который станок назвал сам','A technical break enters Andon only after 15 minutes. Set the last field to 0 to disable Telegram messages.'],
    ['Ключ показывается один раз','The key is shown only once. Copy it now and give it to the 1C integrator:']
  ];
  const patterns = [
    [/^(пн|вт|ср|чт|пт|сб|вс) · (сегодня|выходной)$/,(_,d,label)=>`${dictionary[d]} · ${dictionary[label]}`],
    [/^Найдено: (\d+)$/,(_,n)=>`Found: ${n}`],
    [/^изделий: (\d+)$/,(_,n)=>`products: ${n}`],
    [/^без изделия: (\d+)$/,(_,n)=>`without product: ${n}`],
    [/^(1С|нет в 1С) · (.+)$/,(_,source,rest)=>`${source==='1С'?'1C':'not in 1C'} · ${rest.replaceAll('шт','pcs').replaceAll('ст.-дн.','machine-days').replaceAll('не в плане','unscheduled')}`],
    [/^(\d+) ст.-дн\.$/,(_,n)=>`${n} machine-days`],
    [/^отстаём на (.+) дн\.$/,(_,n)=>`${n} days behind`],
    [/^([\d.,\s]+) ч ([\d.,\s]+) мин ([\d.,\s]+) с$/,(_,h,m,s)=>`${h} h ${m} min ${s} s`],
    [/^([\d.,\s]+) ч ([\d.,\s]+) мин$/,(_,h,m)=>`${h} h ${m} min`],
    [/^([\d.,\s]+) шт(.*)$/,(_,n,rest)=>`${n} pcs${rest.replace('норма','target')}`],
    [/^([\d.,\s]+) из ([\d.,\s]+)$/,(_,a,b)=>`${a} of ${b}`],
    [/^([\d.,\s]+) (заказов|заказа|заказ)$/,(_,n)=>`${n} orders`],
    [/^Ряд (.+)$/,(_,x)=>`Row ${x}`],
    [/^(\d{4}-\d\d-\d\d) · Станки: (\d+) · Остановки: (\d+) · Журнал доступен по (.+)\. (.*)$/,(_,d,n,s,latest,rest)=>`${d} · Machines: ${n} · Stops: ${s} · Log through ${latest}. ${rest.replace('Станки с промежутками без подтверждённого состояния:','Machines with unconfirmed gaps:')}`],
    [/^В плане дни (.+), последняя правка (.+)\. Факт — по (.+)\.$/,(_,period,at,day)=>`Scheduled: ${period}, last edit ${at}. Actual data through ${day}.`],
    [/^(.+) · смена ([ABC])$/,(_,day,shift)=>`${day} · shift ${shift}`],
    [/^(Остановки Toyota|Тикеты за период) · (\d+)$/,(_,label,n)=>`${label==='Остановки Toyota'?'Toyota stops':'Tickets in period'} · ${n}`],
    [/^Клеток: (\d+)(.*)$/,(_,n,rest)=>`Cells: ${n}${rest.replace('заказ','order')}`],
    [/^Скопировано клеток: (\d+)$/,(_,n)=>`Copied cells: ${n}`],
    [/^Выбрано ячеек: (\d+)$/,(_,n)=>`Selected cells: ${n}`],
    [/^(.+) — можно редактировать$/,(_,x)=>`${x} — editable`],
    [/^(.+) — просмотр$/,(_,x)=>`${x} — read only`],
    [/^(.*?)\s*—\s*сегодня$/,(_,x)=>`${x} — today`],
    [/^(.*?)\s*—\s*выходной$/,(_,x)=>`${x} — day off`],
    [/^История (\w+)$/,(_,x)=>`History ${x}`],
    [/^(Остановы|Работа \(расчёт\)|Неизвестно|Полная длительность|Реакция|Код Toyota|Стиль|Смена):\s*(.*)$/,(_,key,v)=>`${({'Остановы':'Stops','Полная длительность':'Full duration','Реакция':'Response','Код Toyota':'Toyota code','Стиль':'Style'}[key]||dictionary[key]||key)}: ${translateValue(v)}`]
  ];
  const errors = {'Не удалось загрузить данные':'Unable to load data','Не сохранилось':'Could not save',
    'Список пользователей не загрузился':'Unable to load users','История не загрузилась':'Unable to load history',
    'План цеха не загрузился':'Unable to load machine plan','План не загрузился':'Unable to load plan',
    'Отчёт не загрузился':'Unable to load report','Не получилось':'Action failed','Не создался':'Could not create',
    'Заправка не загрузилась':'Unable to load setup','Простои не загрузились':'Unable to load downtime',
    'Тикеты не загрузились':'Unable to load tickets','Новый пароль не сохранился':'Could not save new password'};
  const reverse=new Map(Object.entries(dictionary).map(([ru,en])=>[en,ru]));
  let language='ru';try{language=localStorage.getItem('mes-language')==='en'?'en':'ru';}catch(e){}
  function translateValue(value){
    if(dictionary[value])return dictionary[value];
    for(const [prefix,text] of help)if(value.startsWith(prefix))return text;
    for(const [pattern,fn] of patterns)if(pattern.test(value))return value.replace(pattern,fn);
    for(const [ru,en] of Object.entries(errors))if(value.startsWith(ru+':'))return en+': '+translateValue(value.slice(ru.length+1).trim());
    return value;
  }
  function t(value){
    const source=String(value??'');if(language==='ru')return source;
    const key=source.replace(/\s+/g,' ').trim(), translated=translateValue(key);
    if(translated===key)return source;
    if(reverse.size>12000)reverse.clear();reverse.set(translated,key);
    return source.slice(0,source.length-source.trimStart().length)+translated+source.slice(source.trimEnd().length);
  }
  const originals=new WeakMap(),attributes=new WeakMap();
  const skip='script,style,input,textarea,code,pre,[contenteditable],[data-i18n-skip],.lp-product,.nt,.keybox,#oc-json,#lp-order-list,#lp-d-prod,#lp-d-hint,#pl-products,#u-table tbody td:nth-child(1),#u-table tbody td:nth-child(2),#op-table tbody td:nth-child(1),#op-table tbody td:nth-child(2),#pl-table tbody td:nth-child(2),#ppt-prod tbody td:first-child,#ppt-days tbody td:nth-child(4)';
  function translateText(node){
    if(!node.parentElement||node.parentElement.closest(skip))return;
    let memo=originals.get(node);
    if(!memo||node.data!==memo.rendered){const normalized=node.data.replace(/\s+/g,' ').trim();memo={source:reverse.get(normalized)||node.data,rendered:node.data};}
    const next=language==='en'?t(memo.source):memo.source;
    if(node.data!==next)node.data=next;memo.rendered=next;originals.set(node,memo);
  }
  function translateAttributes(el){
    if(el.closest('[data-i18n-skip],.lp-product,.nt,#oc-json'))return;
    const memo=attributes.get(el)||{};
    for(const key of ['title','placeholder','aria-label']){
      const current=el.getAttribute(key);if(current===null)continue;
      if(!memo[key]||current!==memo[key].rendered)memo[key]={source:reverse.get(current)||current,rendered:current};
      const next=language==='en'?t(memo[key].source):memo[key].source;
      if(current!==next)el.setAttribute(key,next);memo[key].rendered=next;
    }attributes.set(el,memo);
  }
  let observer=null,scheduled=false;const pending=new Set();
  const options={subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','placeholder','aria-label']};
  function translate(root=document.body){
    if(!root)return;observer?.disconnect();
    try{
      if(root.nodeType===Node.TEXT_NODE){translateText(root);return;}
      if(root.nodeType===Node.DOCUMENT_NODE)root=root.body;
      if(!root)return;
      if(root.nodeType===Node.ELEMENT_NODE)translateAttributes(root);
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode()))translateText(node);
      root.querySelectorAll?.('[title],[placeholder],[aria-label]').forEach(translateAttributes);
    }finally{if(observer&&document.body)observer.observe(document.body,options);}
  }
  function setLanguage(next){
    if(!['ru','en'].includes(next))return;
    language=next;try{localStorage.setItem('mes-language',next);}catch(e){}
    document.documentElement.lang=next;translate();
    window.dispatchEvent(new CustomEvent('mes-language-change',{detail:{language:next}}));
  }
  window.MesI18n={get language(){return language;},setLanguage,t,translate};
  document.documentElement.lang=language;
  function start(){
    translate();observer=new MutationObserver(records=>{
      for(const r of records){
        if(r.type==='childList'){for(const n of r.addedNodes)pending.add(n);}
        else pending.add(r.target);
      }
      if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{
        scheduled=false;const roots=[...pending];pending.clear();
        for(const root of roots)if(root.isConnected)translate(root);
      });
    });observer.observe(document.body,options);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
