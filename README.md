# Shorts Metrics Collector (MVP)

Скрипт собирает метрики YouTube Shorts через YouTube Data API v3 под развлекательную нишу.

## Что уже умеет
- Ищет короткие видео (`videoDuration=short`) по запросу.
- Поддерживает сбор **до 100 роликов за запуск** (пагинация).
- Приоритетно полезен для анализа по лайкам/комментариям:
  - `likeCount`
  - `commentCount`
  - `top_comment_like_count`
  - вычисляемый `engagement_score = likes*2 + comments*3`
- Дополнительно собирает `viewCount`, `publishedAt`, канал и язык.
- Сохраняет результаты в `JSON` и `CSV`.
- Сортирует ролики по вовлечению (сначала самые перспективные).

## Быстрый старт (куда вставлять ключ)
1) Открой терминал в папке проекта:
```bash
cd /workspace/Test2
```

2) Создай файл `.env` рядом с `README.md` и `src/`:
```bash
cp .env.example .env
```

3) Открой `.env` и вставь ключ в эту строку:
```env
YOUTUBE_API_KEY=ВСТАВЬ_СЮДА_СВОЙ_КЛЮЧ
```
Пример файла `/workspace/Test2/.env`:
```env
YOUTUBE_API_KEY=AIza...твoй_ключ...
```

4) Запусти сбор:
```bash
python3 src/collect_shorts_metrics.py --query "смешные видео" --max-results 30 --relevance-language ru --region-code RU
```

5) Результат появится в папке `data/` (`.json` и `.csv`).

## Настройка
1) Создай `.env`:
```bash
cp .env.example .env
```

2) Вставь YouTube API ключ в `.env`:
```env
YOUTUBE_API_KEY=your_key_here
```

> Не коммить `.env` в git.

## Запуск
### Рекомендованный режим (развлекательные RU shorts, 30 шт)
```bash
python src/collect_shorts_metrics.py --max-results 30
```

### До 100 за запуск
```bash
python src/collect_shorts_metrics.py --query "смешные видео" --max-results 100 --relevance-language ru --region-code RU
```

### Пример для EN
```bash
python src/collect_shorts_metrics.py --query "funny shorts" --max-results 50 --relevance-language en --region-code US
```

## Запуск раз в час
Добавь в cron:
```cron
0 * * * * cd /workspace/Test2 && /usr/bin/python3 src/collect_shorts_metrics.py --query "смешные видео" --max-results 30 --relevance-language ru --region-code RU --output data/hourly/shorts_$(date +\%Y\%m\%d_\%H\%M)
```

## Формат выходных файлов
- `data/<name>.json`
- `data/<name>.csv`

Поля:
- `video_id`, `title`, `channel_title`, `published_at`, `default_language`
- `view_count`, `like_count`, `comment_count`
- `engagement_score`
- `top_comment_text`, `top_comment_like_count`
- `collected_at_utc`

## Что дальше
- Добавить расписание через systemd timer/Airflow.
- Добавить дедупликацию роликов между hourly-запусками.
- Добавить отдельный отчёт с top-10 по `engagement_score`.

## Если ошибка `HTTP Error 400: Bad Request`
Попробуй запуск без языковых/региональных фильтров:
```bash
python src/collect_shorts_metrics.py --query "смешные видео" --max-results 30 --relevance-language "" --region-code ""
```

Проверь также:
- ключ действительно вставлен в `.env` (`YOUTUBE_API_KEY=...`),
- в Google Cloud включен **YouTube Data API v3**,
- у API key нет ограничений, которые блокируют запросы с твоего ПК (IP/HTTP referrer).

