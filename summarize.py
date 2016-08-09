#!/usr/bin/env python
"""
test.py - initial attempt at automating dn flows using luigi
"""

from collections import Counter
import csv
import hashlib
import json
import logging
import os
import time
from urllib.parse import urlparse

import imagehash
from jinja2 import Environment, PackageLoader
import luigi
from luigi.contrib import redis_store
import networkx as nx
from PIL import Image
from flask.config import Config
import requests

import twarc


UI_URL = 'http://localhost:5000'
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 4  # arbitrary

config = Config(os.path.dirname(__file__))
config.from_pyfile('dnflow.cfg')

logging.getLogger().setLevel(logging.WARN)
logging.getLogger('').setLevel(logging.WARN)
logging.getLogger('luigi-interface').setLevel(logging.WARN)


def time_hash(digits=6):
    """Generate an arbitrary hash based on the current time for filenames."""
    hash = hashlib.sha1()
    hash.update(str(time.time()).encode())
    t = time.localtime()
    dt = '%s%02d%02d%02d%02d' % (t.tm_year, t.tm_mon, t.tm_mday,
                                 t.tm_hour, t.tm_min)
    return '%s-%s' % (dt, hash.hexdigest()[:digits])


def url_filename(url, include_extension=True):
    """Given a full URL, return just the filename after the last slash."""
    parsed_url = urlparse(url)
    fname = parsed_url.path.split('/')[-1]
    if not include_extension:
        fname = fname.split('.')[0]
    return fname


def generate_md5(fname, block_size=2**16):
    m = hashlib.md5()
    with open(fname, 'rb') as f:
        while True:
            buf = f.read(block_size)
            if not buf:
                break
            m.update(buf)
    return m.hexdigest()


class EventfulTask(luigi.Task):

    @staticmethod
    def update_job(date_path, job_id=None, status=None):
        data = {}
        if job_id:
            data['job_id'] = job_id
        if date_path:
            data['date_path'] = date_path
        if status:
            data['status'] = status
        r = requests.put('%s/job/' % UI_URL, data=data)
        if r.status_code in [200, 302]:
            return True
        return False

    @luigi.Task.event_handler(luigi.Event.START)
    def start(task):
        print('### START ###: %s' % task)
        EventfulTask.update_job(date_path=task.search['date_path'],
                                status='START: %s' % task.task_family)

    @luigi.Task.event_handler(luigi.Event.SUCCESS)
    def success(task):
        print('### SUCCESS ###: %s' % task)
        EventfulTask.update_job(date_path=task.search['date_path'],
                                status='FINISHED: %s' % task.task_family)

    @luigi.Task.event_handler(luigi.Event.PROCESSING_TIME)
    def processing_time(task, processing_time):
        print('### PROCESSING TIME ###: %s, %s' % (task, processing_time))

    @luigi.Task.event_handler(luigi.Event.FAILURE)
    def failure(task, exc):
        print('### FAILURE ###: %s, %s' % (task, exc))
        EventfulTask.update_job(date_path=task.search['date_path'],
                                status='START: %s' % task.task_family)


class FetchTweets(EventfulTask):
    search = luigi.DictParameter()

    def output(self):
        fname = 'data/%s/tweets.json' % self.search['date_path']
        return luigi.LocalTarget(fname)

    def run(self):
        term = self.search['term']
        lang = self.search['lang']
        count = self.search['count']
        t = twarc.Twarc(
            consumer_key=config['TWITTER_CONSUMER_KEY'],
            consumer_secret=config['TWITTER_CONSUMER_SECRET'],
            access_token=self.search['token'],
            access_token_secret=self.search['secret']
        )
        with self.output().open('w') as fh:
            i = 0
            for tweet in t.search(term, lang=lang):
                i += 1
                if i > count:
                    break
                fh.write(json.dumps(tweet) + '\n')


class CountHashtags(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-hashtags.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            c.update([ht['text'].lower()
                      for ht in tweet['entities']['hashtags']])
        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['hashtag', 'count'])
            writer.writeheader()
            for ht, count in c.items():
                writer.writerow({'hashtag': ht, 'count': count})


class EdgelistHashtags(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'edgelist-hashtags.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        """Each edge is a tuple containing (screen_name, mentioned_hashtag)"""
        with self.output().open('w') as fp_csv:
            writer = csv.DictWriter(fp_csv, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['user', 'hashtag'])
            writer.writeheader()
            for tweet_str in self.input().open('r'):
                tweet = json.loads(tweet_str)
                for ht in tweet['entities']['hashtags']:
                    writer.writerow({'user': tweet['user']['screen_name'],
                                     'hashtag': ht['text'].lower()})


class CountUrls(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-urls.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            c.update([url['expanded_url'].lower()
                      for url in tweet['entities']['urls']])
        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['url', 'count'])
            writer.writeheader()
            for url, count in c.items():
                writer.writerow({'url': url, 'count': count})


class CountDomains(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-domains.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            c.update([urlparse(url['expanded_url']).netloc.lower()
                      for url in tweet['entities']['urls']])
        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['url', 'count'])
            writer.writeheader()
            for url, count in c.items():
                writer.writerow({'url': url, 'count': count})


class CountMentions(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-mentions.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            c.update([m['screen_name'].lower()
                     for m in tweet['entities']['user_mentions']])
        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['screen_name', 'count'])
            writer.writeheader()
            for screen_name, count in c.items():
                writer.writerow({'screen_name': screen_name,
                                 'count': count})


class EdgelistMentions(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'edgelist-mentions.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        """Each edge is a tuple containing (screen_name,
        mentioned_screen_name)"""
        with self.output().open('w') as fp_csv:
            writer = csv.DictWriter(fp_csv, delimiter=',',
                                    fieldnames=('from_user', 'to_user'))
            writer.writeheader()
            for tweet_str in self.input().open('r'):
                tweet = json.loads(tweet_str)
                for mention in tweet['entities']['user_mentions']:
                    writer.writerow({'from_user': tweet['user']['screen_name'],
                                     'to_user': mention['screen_name']})


class CountMedia(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-media.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            c.update([m['media_url']
                     for m in tweet['entities'].get('media', [])
                     if m['type'] == 'photo'])
        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['url', 'file', 'count'])
            writer.writeheader()
            for url, count in c.items():
                writer.writerow({'url': url, 'file': url_filename(url),
                                 'count': count})


class FetchMedia(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return CountMedia(search=self.search)

    def output(self):
        # ensure only one successful fetch for each url
        # unless FetchTweets is called again with a new hash
        fname = self.input().fn.replace('count-media.csv',
                                        'media-checksums-md5.txt')
        return luigi.LocalTarget(fname)

    def run(self):
        dirname = 'data/%s/media' % self.search['date_path']
        os.makedirs(dirname, exist_ok=True)
        # lots of hits to same server, so pool connections
        hashes = []
        session = requests.Session()
        with self.input().open('r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=',')
            for row in reader:
                fname = url_filename(row['url'])
                if len(fname) == 0:
                    continue
                r = session.get(row['url'])
                if r.ok:
                    full_name = '%s/%s' % (dirname, fname)
                    with open(full_name, 'wb') as media_file:
                        media_file.write(r.content)
                    md5 = generate_md5(full_name)
        with self.output().open('w') as f:
            for md5, h in hashes:
                f.write('%s %s\n' % (md5, h))


class MatchMedia(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchMedia(search=self.search)

    def output(self):
        fname = self.input().fn.replace('media-checksums-md5.txt',
                                        'media-graph.json')
        return luigi.LocalTarget(fname)

    def run(self):
        date_path = self.search['date_path']
        files = sorted(os.listdir('data/%s/media' % date_path))
        hashes = {}
        matches = []
        g = nx.Graph()
        for i in range(len(files)):
            f = files[i]
            fn = 'data/%s/media/%s' % (date_path, f)
            ahash = imagehash.average_hash(Image.open(fn))
            dhash = imagehash.dhash(Image.open(fn))
            phash = imagehash.phash(Image.open(fn))
            hashes[f] = {'ahash': ahash, 'dhash': dhash, 'phash': phash}
            for j in range(0, i):
                f2name = files[j]
                f2 = hashes[f2name]
                sumhash = sum([ahash - f2['ahash'],
                               dhash - f2['dhash'],
                               phash - f2['phash']])
                if sumhash <= 40:
                    matches.append([f, files[j],
                                    ahash - f2['ahash'],
                                    dhash - f2['dhash'],
                                    phash - f2['phash'],
                                    sumhash])
                    g.add_edge(f, f2name)
        with self.output().open('w') as fp_graph:
            components = list(nx.connected_components(g))
            # Note: sets are not JSON serializable
            d = []
            for s in components:
                d.append(list(s))
            logging.debug(' - = - = - = GRAPH HERE - = - = - = -')
            logging.debug(d)
            json.dump(d, fp_graph, indent=2)


class CountFollowers(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'count-followers.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        users = {}
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            user = tweet['user']['screen_name']
            followers = tweet['user']['followers_count']
            users[user] = followers

        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['user', 'count'])
            writer.writeheader()
            for user, count in users.items():
                writer.writerow({'user': user, 'count': count})


class FollowRatio(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'follow-ratio.csv')
        return luigi.LocalTarget(fname)

    def run(self):
        users = {}
        for tweet_str in self.input().open('r'):
            tweet = json.loads(tweet_str)
            user = tweet['user']['screen_name']
            followers = int(tweet['user']['followers_count'])
            following = int(tweet['user']['friends_count'])
            if following > 0:
                r = followers / float(following)
                users[user] = r

        with self.output().open('w') as fp_counts:
            writer = csv.DictWriter(fp_counts, delimiter=',',
                                    quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=['user', 'count'])
            writer.writeheader()
            for user, r in users.items():
                writer.writerow({'user': user, 'count': r})


class SummaryHTML(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = 'data/%s/summary.html' % self.search['date_path']
        return luigi.LocalTarget(fname)

    def run(self):
        env = Environment(loader=PackageLoader('web'))
        t = env.get_template('summary.html')
        title = 'Summary for search "%s"' % self.term
        t.stream(title=title).dump(self.output().fn)


class SummaryJSON(EventfulTask):
    search = luigi.DictParameter()

    def requires(self):
        return FetchTweets(search=self.search)

    def output(self):
        fname = self.input().fn.replace('tweets.json', 'summary.json')
        return luigi.LocalTarget(fname)

    def run(self):
        c = Counter()
        num_tweets = 0
        for tweet_str in self.input().open('r'):
            num_tweets += 1
            tweet = json.loads(tweet_str)
            c.update([m['media_url']
                     for m in tweet['entities'].get('media', [])
                     if m['type'] == 'photo'])
        summary = {
                'path': self.search['date_path'],
                'date': time.strftime('%Y-%m-%d %H:%M:%S',
                                      time.localtime()),
                'num_tweets': num_tweets,
                'term': self.search['term']
                }
        with self.output().open('w') as fp_summary:
            json.dump(summary, fp_summary)


class PopulateRedis(EventfulTask):
    search = luigi.DictParameter()

    def _get_target(self):
        return redis_store.RedisTarget(host=REDIS_HOST, port=REDIS_PORT,
                                       db=REDIS_DB,
                                       update_id=self.search['date_path'])

    def requires(self):
        return MatchMedia(search=self.search)

    def output(self):
        return self._get_target()

    def run(self):
        date_path = self.search['date_path']
        r = redis_store.redis.StrictRedis(host='localhost')
        # Assume tweets.json exists, earlier dependencies require it
        tweet_fname = 'data/%s/tweets.json' % date_path
        for tweet_str in open(tweet_fname, 'r'):
            tweet = json.loads(tweet_str)
            pipe = r.pipeline()
            # baseline data
            pipe.sadd('tweets:%s' % date_path, tweet['id'])
            for hashtag in [ht['text'].lower() for ht in
                            tweet['entities']['hashtags']]:
                pipe.zincrby('count:hashtags:%s' % date_path,
                             hashtag, 1)
                pipe.sadd('hashtag:%s:%s' % (hashtag, date_path),
                          tweet['id'])
            for mention in [m['screen_name'].lower() for m in
                            tweet['entities']['user_mentions']]:
                pipe.zincrby('count:mentions:%s' % date_path,
                             mention, 1)
                pipe.sadd('mention:%s:%s' % (mention, date_path),
                          tweet['id'])
            for photo_url in [m['media_url']
                              for m in tweet['entities'].get('media', [])
                              if m['type'] == 'photo']:
                photo_id = url_filename(photo_url, include_extension=False)
                pipe.zincrby('count:photos:%s' % date_path, photo_id, 1)
                pipe.sadd('photo:%s:%s' % (photo_id, date_path),
                          tweet['id'])
            pipe.execute()

        photo_matches_fname = 'data/%s/media-graph.json' % date_path
        photo_matches = json.load(open(photo_matches_fname))
        if photo_matches:
            pipe = r.pipeline()
            # each set of related images
            for photo_match in photo_matches:
                photo_ids = [pm.split('.')[0] for pm in photo_match]
                # each id in the set needs a lookup key
                for i in range(len(photo_match)):
                    photo_id = photo_ids[i]
                    pipe.sadd('photomatch:%s:%s' % (photo_id, date_path),
                              *photo_ids)
            pipe.execute()
        r.sadd('cacheproc', date_path)
        target = self._get_target()
        target.touch()

    def complete(self):
        target = self._get_target()
        return target.exists()


class RunFlow(EventfulTask):
    date_path = time_hash()
    jobid = luigi.IntParameter()
    term = luigi.Parameter()
    count = luigi.IntParameter(default=1000)
    token = luigi.Parameter()
    secret = luigi.Parameter()

    def requires(self):
        search = {
            "date_path": self.date_path,
            "job_id": self.jobid,
            "term": self.term,
            "count": self.count,
            "token": self.token,
            "secret": self.secret,
            "lang": "en"
        }
        EventfulTask.update_job(job_id=search['job_id'], date_path=search['date_path'])
        yield CountHashtags(search=search)
        yield SummaryJSON(search=search)
        yield EdgelistHashtags(search=search)
        yield CountUrls(search=search)
        yield CountDomains(search=search)
        yield CountMentions(search=search)
        yield CountFollowers(search=search)
        yield FollowRatio(search=search)
        yield EdgelistMentions(search=search)
        yield PopulateRedis(search=search)
        yield MatchMedia(search=search)
        EventfulTask.update_job(date_path=search['date_path'], status='SUCCESS')
