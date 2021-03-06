import time
import socket
import json
import praw
import os
import random
import pickle
import sys

from threading import Thread

# Control center
irc_settings = {
  'nick':     'chemo',
  'server':   'irc.amazdong.com',
  'port':     6667,
  'channels': ['#interns', '#chemo']
#  'server':   'irc.tddirc.net',
#  'port':     6667,
#  'channels': ['#thunked', '#chemo']
}

#irc_settings = {
#  'nick': 'chemo',
#  'server': 'irc.tddirc.net',
#  'port': 6667,
#  'channels': ['#thunked']
#}

def save(filename, object):
  with open(filename, 'w') as serializer:
    pickle.dump(object, serializer)

# Load worker bees from file
if os.path.exists('workers'):
  with open('workers') as deserializer:
    workers = pickle.load(deserializer)
else:
  # Provide some starter workers
  workers = [
    {'name': 'aniravigali', 'password': 'e269201c4f025659de7072f73fb4c433'},
    {'name': 'oprahversiontwo', 'password': 'a1cb02bf6d240de3338e72b5f0d3f268'},
    {'name': 'japlandian', 'password': '6f2f01539468a88f60877828b0312b04'}
  ]

  # And start the file for next time
  save('workers', workers)

# Status
queued_jobs = []
jobs_completed = True

# Stats
if os.path.exists('stats'):
  with open('stats') as deserializer:
    stats = pickle.load(deserializer)
else:
  stats = {
    'upvotes':   0,
    'downvotes': 0,
    'jobs':      0
  }
  save('stats', stats)

def handle_queue():
  global queued_jobs # lol
  recent_success = False
  while True:
    if recent_success:
      time.sleep(random.randint(40, 250))

    if queued_jobs and len(queued_jobs) > 0:
      # Take the FIRST-QUEUED job (at the start, because we append for new jobs)
      job = queued_jobs.pop(0)
      if 'worker' in job.keys() and 'action' in job.keys() and 'url' in job.keys():
        print('Executing task: ' + str(job))
        recent_success = do_task(job['worker'], job['action'], job['url'])

# Logic for connecting to IRC
def connect_to_irc(settings):
  irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  irc.connect( (settings['server'], settings['port']) )
  irc.send(' '.join(['USER', \
    settings['nick'], settings['nick'], settings['nick'], settings['nick'], \
    ':chemo']) + "\r\n")
  irc.send(' '.join(['NICK', settings['nick']]) + "\r\n")
  connection = irc.makefile('r', 0)
  return irc, connection

def send_irc_message(irc, channel, message):
  irc.send(' '.join(['PRIVMSG', channel, ':' + str(message)]) + "\r\n")

# Logic for doing tasks
def do_task(worker, action, url):
  global stats
  try:
    r = praw.Reddit(user_agent=worker['name'])
    r.login(worker['name'], worker['password'])

    # Kill trailing slashes
    if url[-1] == '/':
      url = url[:-1]

    c = r.get_submission(url=url)

    # If this is a comment job, grab the first comment
    if url.count('/') > 7:
      c = c.comments[0]

    if action == 'upvote':
      c.upvote()
      stats['upvotes'] = stats['upvotes'] + 1
    elif action == 'downvote':
      c.downvote()
      stats['downvotes'] = stats['downvotes'] + 1
    result = True
  except:
    print('failed voting!')
    print(sys.exc_info()[0])
    result = False

  save('stats', stats)
  return result

def queue_jobs_for(workers, action, url):
  global queued_jobs
  global jobs_completed
  global stats
  for worker in workers:
    job = {'worker': worker, 'action': action, 'url': url}
    stats['jobs'] = stats['jobs'] + 1
    print('Queuing job: ' + str(job))
    queued_jobs.append(job)
  jobs_completed = False

# Start up job queue handler
queue_handler = Thread(target = handle_queue)
queue_handler.daemon = True
queue_handler.start()

# Main thread
irc, connection = connect_to_irc(irc_settings)
for line in connection:
  split = line.split(' ')

  if len(split) > 1 and split[0] == 'PING':
    irc.send(' '.join(['PONG', split[1]]) + "\r\n")
    continue

  if len(split) > 1 and (split[1] == '376' or split[1] == '422'):
    for channel in irc_settings['channels']:
      irc.send(' '.join(['JOIN', channel]) + "\r\n")
    continue

  if not jobs_completed and len(queued_jobs) == 0:
    jobs_completed = True
    send_irc_message(irc, irc_settings['channels'][0], 'All jobs completed.')

  if len(split) > 3 and split[1] == 'PRIVMSG':
    user = split[0][1:] # dru!dru@host
    user = user[0:user.find('!')] # dru
    channel = split[2]
    message = ' '.join(split[3:])[1:].rstrip()
    command = message[0:message.find(' ')] if message.find(' ') > -1 else message
    params = message[message.find(' ') + 1:]

    print "<" + user + "> " + message

    # Add new workers automatically
    if user == '^' and message[0:8] == '{"ok":1,':
      try:
        user_hash = json.loads(message)
        if 'name' in user_hash.keys() and 'password' in user_hash.keys():
          workers.append(user_hash)
          save('workers', workers)
      except:
        print("Couldn't parse worker details from ^: " + message)

    # Handle commands
    if command == '!add':
      try:
        user_hash = json.loads(params)
        if 'name' in user_hash.keys() and 'password' in user_hash.keys():
          workers.append(user_hash)

        save('workers', workers)
      except:
        send_irc_message(irc, channel, "Couldn't parse worker details.")

    elif command == '!workers':
      send_irc_message(irc, channel, 'There are ' + str(len(workers)) + ' workers')

    elif command == '!queue':
      send_irc_message(irc, channel, str(len(queued_jobs)) + ' jobs in queue')

    elif command == '!downvote':
      sample_size = min(20, len(workers))
      queue_jobs_for(random.sample(workers, sample_size), 'downvote', params)
      send_irc_message(irc, channel, 'Queueing ' + str(sample_size) + ' downvotes for ' + params)

    elif command == '!upvote':
      sample_size = min(20, len(workers))
      queue_jobs_for(random.sample(workers, sample_size), 'upvote', params)
      send_irc_message(irc, channel, 'Queueing ' + str(sample_size) + ' upvotes for ' + params)

    elif command == '!stats' or command == '!status':
      send_irc_message(irc, channel, ''.join([str(len(queued_jobs)) + ' jobs queued right now across ',
        str(len(workers)) + ' workers, ',
        str(stats['jobs'] - len(queued_jobs)) + ' jobs completed, ',
        str(stats['upvotes']) + ' upvotes given, ',
        str(stats['downvotes']) + ' downvotes given']))
