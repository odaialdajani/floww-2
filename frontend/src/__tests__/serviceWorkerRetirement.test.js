import { readFileSync } from 'fs';
import { join } from 'path';
import { createContext, Script } from 'vm';

const publicDirectory = join(__dirname, '../../public');
const page = new DOMParser().parseFromString(
  readFileSync(join(publicDirectory, 'index.html'), 'utf8'),
  'text/html',
);
const inlineScripts = Array.from(page.querySelectorAll('script:not([src])'))
  .map((script) => new Script(script.textContent));
const retiredWorker = new Script(
  readFileSync(join(publicDirectory, 'service-worker.js'), 'utf8'),
);

function loadPage(hostname, serviceWorker, debug = false) {
  const loadListeners = [];
  const context = createContext({
    window: {
      location: { hostname },
      __SW_DEBUG__: debug,
      addEventListener(type, listener) {
        if (type === 'load') loadListeners.push(listener);
      },
    },
    navigator: { serviceWorker },
    localStorage: { getItem: () => null },
    document: { documentElement: { setAttribute() {} } },
    console: { log() {} },
  });
  inlineScripts.forEach((script) => script.runInContext(context, { timeout: 1000 }));
  loadListeners.forEach((listener) => listener());
}

describe('retired service worker', () => {
  test.each([
    ['floww-settings.localhost', false],
    ['app.floww.example', false],
    ['localhost', false],
    ['127.0.0.1', false],
    ['[::1]', false],
    ['localhost', true],
  ])('does not register on repeated page loads at %s (debug=%s)', (hostname, debug) => {
    const serviceWorker = {
      register: jest.fn().mockResolvedValue({ scope: '/' }),
    };

    loadPage(hostname, serviceWorker, debug);
    loadPage(hostname, serviceWorker, debug);

    expect(serviceWorker.register).not.toHaveBeenCalled();
  });

  test('an existing worker clears old caches and retires without restarting on its reload', async () => {
    const listeners = {};
    const oldCaches = new Map([['floww-v2', {}], ['floww-v4', {}]]);
    const serviceWorker = {
      register: jest.fn().mockResolvedValue({ scope: '/' }),
    };
    const client = {
      url: 'https://app.floww.example/?page=heatseeker',
      navigate: jest.fn(() => {
        loadPage('app.floww.example', serviceWorker);
        return Promise.resolve(client);
      }),
    };
    let registered = true;
    const self = {
      addEventListener(type, listener) { listeners[type] = listener; },
      skipWaiting: jest.fn(),
      clients: {
        claim: jest.fn().mockResolvedValue(undefined),
        matchAll: jest.fn().mockResolvedValue([client]),
      },
      registration: {
        unregister: jest.fn(async () => { registered = false; return true; }),
      },
    };
    retiredWorker.runInNewContext({
      self,
      caches: {
        keys: async () => Array.from(oldCaches.keys()),
        delete: async (key) => oldCaches.delete(key),
      },
    }, { timeout: 1000 });

    listeners.install();
    let retirement;
    listeners.activate({ waitUntil(promise) { retirement = promise; } });
    await retirement;

    expect(self.skipWaiting).toHaveBeenCalledTimes(1);
    expect(oldCaches.size).toBe(0);
    expect(self.clients.claim).toHaveBeenCalledTimes(1);
    expect(self.registration.unregister).toHaveBeenCalledTimes(1);
    expect(registered).toBe(false);
    expect(self.clients.matchAll).toHaveBeenCalledWith({ type: 'window' });
    expect(client.navigate).toHaveBeenCalledTimes(1);
    expect(client.navigate).toHaveBeenCalledWith(client.url);
    expect(serviceWorker.register).not.toHaveBeenCalled();

    loadPage('app.floww.example', serviceWorker);
    expect(serviceWorker.register).not.toHaveBeenCalled();
    expect(client.navigate).toHaveBeenCalledTimes(1);
  });
});
