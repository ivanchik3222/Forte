# Forte case — frontend

Стартовая основа для кейса Forte: Create React App, React + TypeScript, Tailwind CSS v4 и Zustand. Интерфейс демонстрационный и не является банковским продуктом.

## Запуск

Нужен Node.js и npm. Из папки `frontend`:

```bash
npm install
npm start
```

Приложение откроется на `http://localhost:3000`. Для входа запустите соседний `backend` на `http://localhost:6767` и используйте учётную запись этого локального API. Браузер обращается к backend напрямую по его отдельному URL.

```bash
npm run build
npm test -- --watch=false
```

`npm start` сначала генерирует Tailwind CSS, затем одновременно запускает наблюдение за CSS и dev-сервер CRA. `npm run build` генерирует CSS перед production-сборкой. Сгенерированный `src/styles/generated.css` не хранится в Git.

## Настройка API

Клиент по умолчанию обращается к `http://localhost:6767/api`. Для другого хоста задайте `REACT_APP_API_URL` в `.env.local` по образцу `.env.example` и перезапустите dev-сервер. Значение встраивается в production-сборку. Адрес должен быть доступен из браузера пользователя, а backend должен разрешать URL фронтенда через `CORS_ORIGINS`.

Для запуска в Docker используйте корневой `compose.yaml`: из корня проекта выполните `docker compose up -d --build frontend`. Порт задаётся через `FRONTEND_PORT` в корневом `.env`, адрес API для сборки — через `REACT_APP_API_URL`.

## Структура

| Путь | Назначение |
| --- | --- |
| `src/api/client.ts` | Типы и единая функция HTTP-запросов |
| `src/store/useAuthStore.ts` | Zustand-состояние авторизации |
| `src/components/LoginPanel.tsx` | Пример формы входа через backend |
| `src/styles/input.css` | Tailwind v4, токены цвета и базовые стили |
| `src/App.tsx` | Стартовый адаптивный экран |

Токены сессии хранятся только в памяти вкладки: при обновлении страницы требуется повторный вход. В этом шаблоне реализован вход, но не продление сессии, регистрация и другие банковские сценарии. Не вводите данные реального банковского аккаунта.

Create React App оставлен по требованию проекта. Он официально признан устаревшим; при дальнейшем развитии стоит отдельно запланировать миграцию сборки.
