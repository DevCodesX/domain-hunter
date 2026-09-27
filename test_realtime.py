if __name__ == '__main__':
    from pytrends.request import TrendReq
    pytrends = TrendReq(hl='en-US', tz=360)
    try:
        df = pytrends.realtime_trending_searches(pn='US', cat='t')
        print(df.head(3).to_dict('records'))
    except Exception as e:
        print("Realtime trends error:", e)
