# FopKit

```
FopKit/
├── README.md                        # цей опис папок
├── .cursor/
│   ├── rules/
│   │   ├── language.mdc             # rules і skills англійською, README і вимоги українською
│   │   ├── project.mdc              # правило, поки не застосовується
│   │   ├── readme.mdc               # при новому файлі дописувати його в цей README
│   │   └── requirements.mdc         # єдине ТЗ в requirements/tz.md, оновлювати його
│   └── skills/project/SKILL.md      # skill, поки не викликається сам
├── design/
│   └── index.html                   # драфт головної сторінки, синій варіант
├── src/                             # код сервісу
│   ├── .dockerignore                # що не потрапляє в Docker-образ
│   ├── .env.example                 # шаблон налаштувань сервера без справжніх значень
│   ├── .gitignore                   # що не потрапляє в git: .env, база, віртуальне середовище
│   ├── Caddyfile                    # HTTPS і домен, передає запити застосунку
│   ├── Dockerfile                   # збірка образу застосунку
│   ├── docker-compose.yml           # запуск застосунку, бази і Caddy разом
│   ├── entrypoint.sh                # міграції бази і старт Gunicorn
│   ├── manage.py                    # команди Django
│   ├── requirements.txt             # Python-залежності
│   ├── package.json                 # JS-залежності для збірки jkurwa.bundle.js
│   ├── build.js                     # esbuild-скрипт: static_src/ → jkurwa.bundle.js
│   ├── static_src/                  # вихідники JS-bundle (не потрапляє в Docker як є)
│   │   ├── jkurwa_entry.js          # точка входу: jkurwa + gost89 + dstu7564
│   │   ├── node_crypto_shim.js      # замінник node:crypto для браузера
│   │   └── fs_shim.js               # заглушка fs (не використовується у браузері)
│   ├── fopkit/                      # налаштування Django-проєкту
│   │   ├── __init__.py              # позначає папку як Python-пакет
│   │   ├── middleware.py            # CSP та інші заголовки безпеки
│   │   ├── settings.py              # налаштування: база, безпека, мова, час
│   │   ├── urls.py                  # кореневі адреси сайту
│   │   └── wsgi.py                  # точка входу для Gunicorn
│   └── ledger/                      # застосунок обліку прибутку і податків
│       ├── __init__.py              # позначає папку як Python-пакет
│       ├── apps.py                  # опис застосунку для Django
│       ├── cabinet.py               # API-клієнт кабінету cabinet.tax.gov.ua
│       ├── forms.py                 # форми прибутку і кабінету з перевірками
│       ├── models.py                # таблиці: користувачі, прибуток, місяці, розрахунки
│       ├── money.py                 # копійки, округлення вгору, формат сум
│       ├── nbu.py                   # курс НБУ, вихідні беруть п'ятницю
│       ├── requisites.py            # реквізити ЄП, ЄСВ, ВВ з таблиць сайту податкової
│       ├── services.py              # розрахунок податків, ЄСВ, синхронізація розрахунків
│       ├── tests.py                 # автоматичні тести
│       ├── urls.py                  # адреси сторінок і дій
│       ├── views.py                 # обробка сторінок і дій користувача
│       ├── migrations/              # зміни структури бази
│       │   ├── __init__.py          # позначає папку як Python-пакет
│       │   ├── 0001_initial.py      # створення таблиць
│       │   ├── 0002_create_bond_user.py # створення користувача bond
│       │   ├── 0003_payment_requisites.py # область, громада і таблиця реквізитів
│       │   ├── 0004_bond_tax_location.py # Львівська область і громада для bond
│       │   └── 0005_tax_settlements.py   # таблиці розрахунків з бюджетом
│       ├── static/ledger/           # стилі і скрипти сторінки
│       │   ├── app.css              # спільні стилі: вкладки, картки розрахунків, КЕП
│       │   ├── app.js               # спільний JS: кабінет, КЕП-секція, діалоги
│       │   ├── dashboard.js         # JS сторінки Облік: місяці, записи, підгонка таблиці
│       │   ├── kep.js               # IndexedDB-сховище ключа КЕП і заглушка підпису
│       │   ├── kep_worker.js        # Web Worker: підпис РНОКПП ключем КЕП для входу в кабінет ДПС
│       │   └── settlements.js       # JS сторінки Розрахунки: картки, кнопка синхронізації
│       ├── templates/ledger/        # HTML-шаблони
│       │   ├── base.html            # мінімальний каркас (head, body)
│       │   ├── page_base.html       # спільна шапка, вкладки, кабінет і KEP для всіх сторінок
│       │   ├── dashboard.html       # сторінка Облік — таблиця місяців і записів
│       │   ├── settlements.html     # сторінка Розрахунки з бюджетом
│       │   ├── requisites.html      # сторінка Реквізити для оплати
│       │   ├── login.html           # сторінка входу
│       │   └── requisites_slip.html # картка реквізитів одного платежу
│       └── templatetags/            # фільтри для шаблонів
│           ├── __init__.py          # позначає папку як Python-пакет
│           └── ledger.py            # формат сум і курсу
└── requirements/                    # описи вимог
    ├── .gitkeep                     # щоб порожня папка збереглась у git
    ├── install.md                   # проста інструкція запуску сайту на хостингу
    ├── stack.md                     # стек і вимоги до хостингу
    └── tz.md                        # технічне завдання FopKit
```
