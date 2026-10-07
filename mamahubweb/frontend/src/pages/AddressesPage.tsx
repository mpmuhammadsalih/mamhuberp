import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AddressMapPicker } from '../components/delivery/AddressMapPicker'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { useDeliveryLocation } from '../context/DeliveryLocationContext'
import { useLocale } from '../i18n/LocaleContext'
import {
  applyDeliveryLocationToForm,
  persistDeliveryLocationToAccount,
} from '../lib/accountAddress'
import { deleteData, getApiErrorMessage, getData, postData } from '../lib/api'
import { storage } from '../lib/storage'
import type { Address } from '../types/api'
import type { DeliveryLocation } from '../types/delivery'

const emptyAddressForm = {
  address_title: 'Home',
  address_type: 'HOME',
  street: '',
  city: 'Doha',
  country: 'Qatar',
  zone: '',
  area: '',
  latitude: null as number | null,
  longitude: null as number | null,
  is_default: false,
}

function formatAddressLine(address: Address) {
  return [address.street, address.area, address.city, address.country]
    .filter(Boolean)
    .filter((part, index, parts) => parts.indexOf(part) === index)
    .join(', ')
}

export function AddressesPage() {
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const { location, openPicker } = useDeliveryLocation()
  const syncedRef = useRef(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(emptyAddressForm)

  const applyMapLocation = useCallback((next: DeliveryLocation) => {
    setForm((prev) => applyDeliveryLocationToForm(prev, next))
  }, [])

  const {
    data: addresses = [],
    isLoading,
    isError,
    error,
    isSuccess,
  } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => getData<Address[]>('/addresses'),
    enabled: storage.hasSession(),
  })

  const saveDeliveryPin = useMutation({
    mutationFn: persistDeliveryLocationToAccount,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['addresses'] }),
  })

  useEffect(() => {
    if (syncedRef.current || !isSuccess || addresses.length > 0 || !location) return
    syncedRef.current = true
    void persistDeliveryLocationToAccount(location)
      .then(() => queryClient.invalidateQueries({ queryKey: ['addresses'] }))
      .catch(() => {
        syncedRef.current = false
      })
  }, [addresses.length, isSuccess, location, queryClient])

  const createAddress = useMutation({
    mutationFn: () => postData('/addresses', form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['addresses'] })
      setShowForm(false)
      setForm(emptyAddressForm)
    },
  })

  const setDefault = useMutation({
    mutationFn: (id: number) => postData(`/addresses/${id}/default`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['addresses'] }),
  })

  const removeAddress = useMutation({
    mutationFn: (id: number) => deleteData(`/addresses/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['addresses'] }),
  })

  if (!storage.hasSession()) {
    return (
      <div className={`${PAGE_CONTAINER} py-12 text-center`}>
        <p className="text-gray-600">{t.account.signInAddresses}</p>
        <Link to="/login" className="mt-4 inline-block text-brand-accent hover:underline">
          {t.auth.signIn}
        </Link>
      </div>
    )
  }

  return (
    <div className={`${PAGE_CONTAINER} py-8`}>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">{t.account.addresses}</h1>
        <button
          type="button"
          onClick={() => setShowForm(!showForm)}
          className="rounded-full bg-brand-accent px-4 py-2 text-sm text-white"
        >
          {showForm ? t.shared.cancel : t.account.addAddress}
        </button>
      </div>

      {showForm && (
        <form
          className="mb-8 space-y-3 rounded-2xl bg-white p-6 shadow-sm"
          onSubmit={(e) => {
            e.preventDefault()
            createAddress.mutate()
          }}
        >
          <div>
            <label htmlFor="address-title" className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.account.addressTitle}
            </label>
            <input
              id="address-title"
              name="address_title"
              placeholder={t.checkout.addressTitlePlaceholder}
              value={form.address_title}
              onChange={(e) => setForm({ ...form, address_title: e.target.value })}
              className="w-full rounded-lg border px-3 py-3 text-base"
              required
            />
          </div>

          <AddressMapPicker
            latitude={form.latitude}
            longitude={form.longitude}
            onResolved={applyMapLocation}
          />

          <div>
            <label htmlFor="address-street" className="mb-1.5 block text-sm font-medium text-slate-700">
              {t.account.addressStreet}
            </label>
            <input
              id="address-street"
              name="street"
              autoComplete="street-address"
              placeholder={t.checkout.streetPlaceholder}
              value={form.street}
              onChange={(e) => setForm({ ...form, street: e.target.value })}
              className="w-full rounded-lg border px-3 py-3 text-base"
              required
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label htmlFor="address-city" className="mb-1.5 block text-sm font-medium text-slate-700">
                {t.account.addressCity}
              </label>
              <input
                id="address-city"
                name="city"
                autoComplete="address-level2"
                placeholder={t.checkout.cityPlaceholder}
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                className="w-full rounded-lg border px-3 py-3 text-base"
                required
              />
            </div>
            <div>
              <label htmlFor="address-zone" className="mb-1.5 block text-sm font-medium text-slate-700">
                {t.account.addressZone}
              </label>
              <input
                id="address-zone"
                name="zone"
                autoComplete="address-level1"
                placeholder={t.checkout.zonePlaceholder}
                value={form.zone}
                onChange={(e) => setForm({ ...form, zone: e.target.value })}
                className="w-full rounded-lg border px-3 py-3 text-base"
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
            />
            {t.checkout.setAsDefault}
          </label>
          <button
            type="submit"
            disabled={createAddress.isPending}
            className="rounded-full bg-brand-accent px-6 py-2 text-white disabled:opacity-50"
          >
            {createAddress.isPending ? t.shared.saving : t.checkout.saveAddress}
          </button>
          {createAddress.isError && (
            <p className="text-sm text-red-600">{getApiErrorMessage(createAddress.error)}</p>
          )}
        </form>
      )}

      {isLoading && <p className="text-gray-500">{t.account.loadingAddresses}</p>}
      {isError && (
        <p className="mb-4 text-sm text-red-600">{getApiErrorMessage(error)}</p>
      )}

      <div className="space-y-4">
        {addresses.map((a) => (
          <div key={a.address_id} className="rounded-2xl bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold">
                  {a.address_title}
                  {a.is_default && (
                    <span className="ml-2 rounded-full bg-pink-100 px-2 py-0.5 text-xs text-brand-accent">
                      {t.shared.default}
                    </span>
                  )}
                </p>
                <p className="text-sm text-gray-600">{formatAddressLine(a)}</p>
              </div>
              <div className="flex gap-2">
                {!a.is_default && (
                  <button
                    type="button"
                    onClick={() => setDefault.mutate(a.address_id)}
                    className="text-sm text-brand-accent"
                  >
                    {t.shared.makeDefault}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removeAddress.mutate(a.address_id)}
                  className="text-sm text-red-600"
                >
                  {t.shared.delete}
                </button>
              </div>
            </div>
          </div>
        ))}

        {!isLoading && !addresses.length && location && (
          <div className="rounded-2xl bg-white p-5 shadow-sm">
            <p className="font-semibold">{location.areaLabel}</p>
            <p className="text-sm text-gray-600">{location.fullLabel}</p>
            <p className="mt-2 text-sm text-gray-500">{t.account.deliveryLocationHint}</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => saveDeliveryPin.mutate(location)}
                disabled={saveDeliveryPin.isPending}
                className="rounded-full bg-brand-accent px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {saveDeliveryPin.isPending ? t.shared.saving : t.account.saveDeliveryLocation}
              </button>
              <button
                type="button"
                onClick={openPicker}
                className="text-sm text-brand-accent"
              >
                {t.delivery.selectLocation}
              </button>
            </div>
            {saveDeliveryPin.isError && (
              <p className="mt-3 text-sm text-red-600">
                {getApiErrorMessage(saveDeliveryPin.error)}
              </p>
            )}
          </div>
        )}

        {!isLoading && !addresses.length && !location && (
          <p className="text-gray-500">{t.account.noAddresses}</p>
        )}
      </div>
    </div>
  )
}
