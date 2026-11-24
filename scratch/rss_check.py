import feedparser

feed = feedparser.parse('https://feeds.bbci.co.uk/sport/football/rss.xml')
print('Всего статей в фиде:', len(feed.entries))
for entry in feed.entries[:5]:
    print(entry.published, '|', entry.title)
