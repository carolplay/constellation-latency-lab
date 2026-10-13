from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from functools import partial
import argparse
parser=argparse.ArgumentParser(description='Serve the built static tools on loopback')
parser.add_argument('--port',type=int,default=8766);parser.add_argument('--directory',default='build/site');args=parser.parse_args()
directory=Path(args.directory).resolve()
if not (directory/'index.html').exists():raise SystemExit('Run python scripts/build_site.py first')
server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(SimpleHTTPRequestHandler,directory=str(directory)))
print(f'Toolkit: http://127.0.0.1:{args.port}',flush=True)
try:server.serve_forever()
except KeyboardInterrupt:server.server_close()
