import requests
import xmltodict
import json

url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"
res = requests.get(url)
parsed = xmltodict.parse(res.content)
items = parsed['rss']['channel']['item']
for item in items[:2]:
    print(item['title'])
