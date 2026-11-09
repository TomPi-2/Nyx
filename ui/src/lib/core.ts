import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { PROTOCOL_VERSION, type Hello, type ServerMessage } from "./protocol";

interface CoreEndpoint {
  port: number;
  token: string;
}

const RETRY_MS = 1000;

/**
 * Conecta con el núcleo por WebSocket y se reconecta solo.
 * El puerto y el token cambian si el núcleo se reinicia, así que se piden de nuevo
 * al proceso principal en cada intento. Devuelve una función para desconectar.
 */
export function connectCore(
  onMessage: (msg: ServerMessage) => void,
  onStatus: (connected: boolean) => void,
): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let retry: ReturnType<typeof setTimeout> | undefined;

  const schedule = () => {
    clearTimeout(retry);
    if (!stopped) retry = setTimeout(() => void connect(), RETRY_MS);
  };

  async function connect() {
    if (stopped) return;
    const endpoint = await invoke<CoreEndpoint | null>("core_endpoint");
    if (!endpoint) return; // llegará «core://ready»
    socket?.close();
    const ws = new WebSocket(`ws://127.0.0.1:${endpoint.port}`);
    socket = ws;
    ws.onopen = () => {
      const hello: Hello = { type: "hello", token: endpoint.token, protocol: PROTOCOL_VERSION };
      ws.send(JSON.stringify(hello));
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(String(event.data)) as ServerMessage;
      if (msg.type === "welcome") onStatus(true);
      onMessage(msg);
    };
    ws.onclose = () => {
      if (socket !== ws) return; // sustituida por una conexión más nueva
      socket = null;
      onStatus(false);
      schedule();
    };
  }

  const unlisten = listen("core://ready", () => void connect());
  void connect();

  return () => {
    stopped = true;
    clearTimeout(retry);
    socket?.close();
    void unlisten.then((off) => off());
  };
}
