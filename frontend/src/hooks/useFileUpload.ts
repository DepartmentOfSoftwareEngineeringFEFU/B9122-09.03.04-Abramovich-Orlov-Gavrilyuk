import { useState, useCallback } from 'react';
import { uploadApi } from '../api/apiService';
import type { UploadedFile } from '../types/wizard';

interface UseFileUploadReturn {
  files: UploadedFile[];
  isUploading: boolean;
  error: string | null;
  addFile: (file: File) => Promise<void>;
  addFiles: (files: File[]) => Promise<void>;
  removeFile: (id: string) => void;
  clearFiles: () => void;
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];

export const useFileUpload = (): UseFileUploadReturn => {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addFile = useCallback(async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError('Неверный формат файла. Допустимы: JPG, PNG, PDF');
      return;
    }
    setIsUploading(true);
    setError(null);
    try {
      const data = await uploadApi.uploadPlanPhoto(file);
      const uploaded: UploadedFile = {
        id: String(data.id ?? data.file_id ?? ''),
        url: String(data.url ?? ''),
        name: file.name,
      };
      setFiles((prev) => [...prev, uploaded]);
    } catch {
      setError('Ошибка загрузки файла');
    } finally {
      setIsUploading(false);
    }
  }, []);

  const addFiles = useCallback(async (newFiles: File[]) => {
    const valid = newFiles.filter((f) => ALLOWED_TYPES.includes(f.type));
    if (valid.length === 0) {
      setError('Неверный формат файла. Допустимы: JPG, PNG, PDF');
      return;
    }
    setIsUploading(true);
    setError(null);
    try {
      const results = await Promise.all(
        valid.map(async (file) => {
          const data = await uploadApi.uploadPlanPhoto(file);
          return {
            id: String(data.id ?? data.file_id ?? ''),
            url: String(data.url ?? ''),
            name: file.name,
          } as UploadedFile;
        })
      );
      setFiles((prev) => [...prev, ...results]);
    } catch {
      setError('Ошибка загрузки файла');
    } finally {
      setIsUploading(false);
    }
  }, []);

  const removeFile = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const clearFiles = useCallback(() => {
    setFiles([]);
  }, []);

  return { files, isUploading, error, addFile, addFiles, removeFile, clearFiles };
};
