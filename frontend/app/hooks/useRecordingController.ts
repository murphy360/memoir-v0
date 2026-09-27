import { useEffect, useRef, useState } from "react";
import { AUDIO_DEVICE_STORAGE_KEY } from "../lib/memoirUi";

type AudioInputDevice = {
  deviceId: string;
  label: string;
};

export function useRecordingController(setStatus: (value: string) => void) {
  const [audioDevices, setAudioDevices] = useState<AudioInputDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [audioLevel, setAudioLevel] = useState(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const levelAnimationRef = useRef<number | null>(null);

  async function refreshAudioDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const inputs = devices
        .filter((device) => device.kind === "audioinput")
        .map((device, index) => ({
          deviceId: device.deviceId,
          label: device.label || `Microphone ${index + 1}`,
        }));

      setAudioDevices(inputs);
      setSelectedDeviceId((current) => {
        if (current && inputs.some((item) => item.deviceId === current)) {
          return current;
        }

        const savedDeviceId = localStorage.getItem(AUDIO_DEVICE_STORAGE_KEY);
        if (
          savedDeviceId &&
          inputs.some((item) => item.deviceId === savedDeviceId)
        ) {
          return savedDeviceId;
        }

        const fallbackDeviceId = inputs[0]?.deviceId || "";
        if (fallbackDeviceId) {
          localStorage.setItem(AUDIO_DEVICE_STORAGE_KEY, fallbackDeviceId);
        } else {
          localStorage.removeItem(AUDIO_DEVICE_STORAGE_KEY);
        }
        return fallbackDeviceId;
      });
    } catch {
      setStatus("Unable to enumerate microphone devices.");
    }
  }

  function stopAudioLevelMonitoring() {
    if (levelAnimationRef.current !== null) {
      cancelAnimationFrame(levelAnimationRef.current);
      levelAnimationRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    setAudioLevel(0);
  }

  function startAudioLevelMonitoring(stream: MediaStream) {
    stopAudioLevelMonitoring();

    const context = new AudioContext();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    audioContextRef.current = context;

    const data = new Uint8Array(analyser.fftSize);

    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        sum += normalized * normalized;
      }
      const rms = Math.sqrt(sum / data.length);
      const scaled = Math.min(1, rms * 4);
      setAudioLevel(scaled);
      levelAnimationRef.current = requestAnimationFrame(tick);
    };

    levelAnimationRef.current = requestAnimationFrame(tick);
  }

  useEffect(() => {
    void refreshAudioDevices();

    const mediaDevices = navigator.mediaDevices;
    const onDeviceChange = () => {
      void refreshAudioDevices();
    };

    mediaDevices.addEventListener("devicechange", onDeviceChange);
    return () => {
      mediaDevices.removeEventListener("devicechange", onDeviceChange);
      stopAudioLevelMonitoring();
    };
  }, []);

  return {
    audioDevices,
    selectedDeviceId,
    setSelectedDeviceId,
    audioLevel,
    refreshAudioDevices,
    startAudioLevelMonitoring,
    stopAudioLevelMonitoring,
  };
}
