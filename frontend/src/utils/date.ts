/**
 * 日付関連のユーティリティ関数
 */

import { format, formatDistanceToNow, parseISO } from 'date-fns'
import { ja } from 'date-fns/locale'

// 日付を相対時間で表示（例：2分前、1時間前）
export function formatRelativeTime(dateString: string): string {
  try {
    const date = parseISO(dateString)
    return formatDistanceToNow(date, {
      addSuffix: true,
      locale: ja
    })
  } catch (error) {
    return 'Invalid date'
  }
}

// 日付を指定フォーマットで表示
export function formatDate(
  dateString: string,
  formatStr: string = 'yyyy/MM/dd HH:mm'
): string {
  try {
    const date = parseISO(dateString)
    return format(date, formatStr, { locale: ja })
  } catch (error) {
    return 'Invalid date'
  }
}

// 日付を日本語フォーマットで表示
export function formatJapaneseDate(dateString: string): string {
  return formatDate(dateString, 'yyyy年MM月dd日 HH:mm')
}

// 時刻のみ表示
export function formatTime(dateString: string): string {
  return formatDate(dateString, 'HH:mm')
}

// 日付のみ表示
export function formatDateOnly(dateString: string): string {
  return formatDate(dateString, 'yyyy/MM/dd')
}

// ISO文字列から Date オブジェクトに変換
export function parseDate(dateString: string): Date {
  return parseISO(dateString)
}

// 現在時刻をISO文字列で取得
export function getCurrentISOString(): string {
  return new Date().toISOString()
}