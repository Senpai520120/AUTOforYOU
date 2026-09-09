'use client';
import { useRef, useState } from 'react';
import Image from 'next/image';
import { localApi } from '@/api/local';
import { LocalListingImage } from '@/lib/types';

interface Props {
  listingId: number;
  initial?: LocalListingImage[];
  onChange?: (imgs: LocalListingImage[]) => void;
}

export default function PhotoUploadBlock({ listingId, initial = [], onChange }: Props) {
  const [images, setImages] = useState<LocalListingImage[]>(initial);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  function update(next: LocalListingImage[]) {
    setImages(next);
    onChange?.(next);
  }

  async function handleFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setError('');
    setUploading(true);
    try {
      const created = await localApi.uploadImages(listingId, files);
      update([...images, ...created]);
    } catch (err: unknown) {
      const apiErr = err as { data?: { detail?: string | string[] } };
      const detail = apiErr?.data?.detail;
      setError(Array.isArray(detail) ? detail.join(' ') : (detail ?? 'Помилка завантаження.'));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function handleDelete(imgId: number) {
    try {
      await localApi.deleteImage(listingId, imgId);
      update(images.filter(i => i.id !== imgId));
    } catch {
      setError('Не вдалося видалити фото.');
    }
  }

  async function handleSetPrimary(imgId: number) {
    try {
      await localApi.setPrimaryImage(listingId, imgId);
      update(images.map(i => ({ ...i, is_primary: i.id === imgId })));
    } catch {
      setError('Не вдалося призначити головне фото.');
    }
  }

  const imgSrc = (img: LocalListingImage) =>
    img.image ?? img.source_url ?? '/placeholder-car.svg';

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">
          Фото ({images.length}/15)
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading || images.length >= 15}
          className="text-sm bg-blue-50 hover:bg-blue-100 disabled:opacity-50 text-blue-700 border border-blue-200 rounded-lg px-3 py-1.5 transition-colors"
        >
          {uploading ? 'Завантаження...' : '+ Додати фото'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={handleFiles}
        />
      </div>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {images.length === 0 ? (
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-slate-200 rounded-xl h-32 flex flex-col items-center justify-center gap-2 text-slate-400 cursor-pointer hover:border-blue-300 hover:text-blue-400 transition-colors"
        >
          <span className="text-3xl">📷</span>
          <span className="text-sm">Клацніть або перетягніть фото (jpg/png/webp, до 8 МБ)</span>
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {images.map(img => (
            <div key={img.id} className="relative group aspect-square rounded-lg overflow-hidden border border-slate-200">
              <Image
                src={imgSrc(img)}
                alt="фото"
                fill
                className="object-cover"
                sizes="150px"
              />
              {img.is_primary && (
                <span className="absolute top-1 left-1 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">
                  Головне
                </span>
              )}
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                {!img.is_primary && (
                  <button
                    type="button"
                    title="Зробити головним"
                    onClick={() => handleSetPrimary(img.id)}
                    className="bg-white/90 hover:bg-white text-blue-700 text-xs font-semibold px-2 py-1 rounded"
                  >
                    Гол.
                  </button>
                )}
                <button
                  type="button"
                  title="Видалити"
                  onClick={() => handleDelete(img.id)}
                  className="bg-white/90 hover:bg-white text-red-600 text-xs font-semibold px-2 py-1 rounded"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
