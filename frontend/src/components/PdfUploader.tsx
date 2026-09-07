// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import { useRef } from 'react';
import { fetchAuthSession } from 'aws-amplify/auth';
import type { UploadedDoc } from '../App';
import { Icon } from './Icon';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000';

interface PdfUploaderProps {
  userId: string;
  knownHashes: Record<string, string>;
  onUploadComplete?: (s3Uris: string[]) => void;
  onDocUpdate?: (id: string, doc: Partial<UploadedDoc> & { name: string; size: number }) => void;
  onNotify?: (message: string, type: 'info' | 'warning' | 'error') => void;
  t: (key: string) => string;
}

/** Compute SHA-256 hash of a file for duplicate detection */
async function hashFile(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export function PdfUploader({ userId, knownHashes, onUploadComplete, onDocUpdate, onNotify, t }: PdfUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles) return;

    const duplicates: string[] = [];
    const filesToUpload: { file: File; hash: string }[] = [];

    // Pre-check local conocido (hashes del backend cargados al login)
    for (const file of Array.from(selectedFiles)) {
      if (file.type !== 'application/pdf') {
        onNotify?.(t('pdf_only'), 'warning');
        continue;
      }
      const hash = await hashFile(file);
      if (knownHashes[hash]) {
        duplicates.push(`${file.name} (${t('duplicate_of')} ${knownHashes[hash]})`);
      } else {
        filesToUpload.push({ file, hash });
      }
    }

    if (duplicates.length > 0) {
      onNotify?.(`${t('duplicates_detected')}:\n${duplicates.join('\n')}`, 'warning');
    }

    if (filesToUpload.length === 0) {
      e.target.value = '';
      return;
    }

    const uploadPromises = filesToUpload.map(async ({ file, hash }) => {
      const fileId = `${Date.now()}-${file.name}`;
      onDocUpdate?.(fileId, { name: file.name, size: file.size, s3Uri: '', status: 'uploading' });

      try {
        // Pedir presigned URL — el backend valida duplicado por hash
        const session = await fetchAuthSession();
        const token = session.tokens?.idToken?.toString() || '';
        const response = await fetch(`${API_URL}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': token },
          body: JSON.stringify({ filename: file.name, userId, fileHash: hash }),
        });

        // 409 = duplicado detectado en backend
        if (response.status === 409) {
          const dupData = await response.json();
          onNotify?.(`${file.name}: ${dupData.message || t('duplicates_detected')}`, 'warning');
          onDocUpdate?.(fileId, { name: file.name, size: file.size, s3Uri: '', status: 'error' });
          return null;
        }

        if (!response.ok) throw new Error('Error obteniendo presigned URL');

        const { uploadUrl, s3Uri } = await response.json();

        const uploadResponse = await fetch(uploadUrl, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/pdf' },
          body: file,
        });
        if (!uploadResponse.ok) throw new Error('Error subiendo archivo a S3');

        onDocUpdate?.(fileId, { name: file.name, size: file.size, s3Uri, status: 'uploaded' });
        return { fileId, s3Uri };
      } catch (error) {
        console.error('Error uploading file:', error);
        onDocUpdate?.(fileId, { name: file.name, size: file.size, s3Uri: '', status: 'error' });
        return null;
      }
    });

    const results = (await Promise.all(uploadPromises)).filter(Boolean) as { fileId: string; s3Uri: string }[];
    const s3Uris = results.map(r => r.s3Uri);
    if (s3Uris.length > 0 && onUploadComplete) onUploadComplete(s3Uris);
    e.target.value = '';
  };

  return (
    <div className="pdf-uploader">
      <div className="section-label">{t('bank_statements')}</div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        onChange={handleFileChange}
        id="pdf-input"
        style={{ display: 'none' }}
      />
      <label htmlFor="pdf-input" className="upload-button">
        <Icon name="document" /> {t('upload_pdfs')}
      </label>
    </div>
  );
}
