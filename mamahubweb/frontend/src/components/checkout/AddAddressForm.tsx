import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { AddressMapPicker } from '../delivery/AddressMapPicker'
import { useLocale } from '../../i18n/LocaleContext'
import { applyDeliveryLocationToForm } from '../../lib/accountAddress'
import { getApiErrorMessage, postData } from '../../lib/api'
import type { Address } from '../../types/api'
import type { DeliveryLocation } from '../../types/delivery'

const emptyForm = {
  address_title: 'Home',
  address_type: 'HOME' as const,
  street: '',
  city: 'Doha',
  country: 'Qatar',
  zone: '',
  area: '',
  latitude: null as number | null,
  longitude: null as number | null,
  is_default: false,
}

interface AddAddressFormProps {
  onSuccess: (address: Address) => void
  onCancel?: () => void
  defaultAsFirst?: boolean
}

export function AddAddressForm({ onSuccess, onCancel, defaultAsFirst = false }: AddAddressFormProps) {
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    ...emptyForm,
    is_default: defaultAsFirst,
  })

  const applyMapLocation = useCallback((next: DeliveryLocation) => {
    setForm((prev) => applyDeliveryLocationToForm(prev, next))
  }, [])

  const createAddress = useMutation({
    mutationFn: () =>
      postData<Address>('/addresses', {
        ...form,
        is_default: defaultAsFirst ? true : form.is_default,
      }),
    onSuccess: (address) => {
      void queryClient.invalidateQueries({ queryKey: ['addresses'] })
      setForm({ ...emptyForm, is_default: defaultAsFirst })
      onSuccess(address)
    },
  })

  return (
    <form
      className="space-y-3 rounded-xl border border-pink-100 bg-pink-50/40 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        createAddress.mutate()
      }}
    >
      <p className="text-sm font-semibold text-gray-800">{t.checkout.newAddress}</p>
      <input
        placeholder={t.checkout.addressTitlePlaceholder}
        value={form.address_title}
        onChange={(e) => setForm({ ...form, address_title: e.target.value })}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
        name="address_title"
        required
      />
      <AddressMapPicker
        latitude={form.latitude}
        longitude={form.longitude}
        onResolved={applyMapLocation}
      />
      <input
        placeholder={t.checkout.streetPlaceholder}
        value={form.street}
        onChange={(e) => setForm({ ...form, street: e.target.value })}
        className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
        name="street"
        autoComplete="street-address"
        required
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          name="city"
          autoComplete="address-level2"
          placeholder={t.checkout.cityPlaceholder}
          value={form.city}
          onChange={(e) => setForm({ ...form, city: e.target.value })}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
          required
        />
        <input
          name="zone"
          autoComplete="address-level1"
          placeholder={t.checkout.zonePlaceholder}
          value={form.zone}
          onChange={(e) => setForm({ ...form, zone: e.target.value })}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm"
        />
      </div>
      {!defaultAsFirst && (
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={form.is_default}
            onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
          />
          {t.checkout.setAsDefault}
        </label>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={createAddress.isPending}
          className="rounded-full bg-brand-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {createAddress.isPending ? t.shared.saving : t.checkout.saveAddress}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600"
          >
            {t.shared.cancel}
          </button>
        )}
      </div>
      {createAddress.isError && (
        <p className="text-sm text-red-600">{getApiErrorMessage(createAddress.error)}</p>
      )}
    </form>
  )
}
