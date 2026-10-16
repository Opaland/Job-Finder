import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { useToast } from '../App.jsx'

export default function ContactsOffre({ company, onContacts }) {
  const [contacts, setContacts] = useState([])
  const [newContact, setNewContact] = useState(null)
  const showToast = useToast()

  const load = () => {
    if (!company) return
    api.contacts(company).then((list) => { setContacts(list); onContacts?.(list) }).catch(() => {})
  }

  useEffect(() => { load() }, [company])

  if (!company) return null

  return (
    <>
      <div className="section-title">Contacts chez {company}</div>
      {contacts.length === 0 && <p className="hint" style={{ margin: '2px 0 6px' }}>Aucun contact enregistré pour cette entreprise.</p>}
      {contacts.map((c) => (
        <div key={c.id} className="actions-row" style={{ margin: '2px 0' }}>
          <span><b>{c.name}</b>{c.role ? ` · ${c.role}` : ''}</span>
          {c.email && <a href={`mailto:${c.email}`}>{c.email}</a>}
          {c.phone && <span className="hint">{c.phone}</span>}
          <button
            className="fav" title="Supprimer ce contact" style={{ fontSize: 14 }}
            onClick={async () => {
              try { await api.deleteContact(c.id); load() } catch (err) { showToast(err.message, true) }
            }}
          >✕</button>
        </div>
      ))}
      {newContact === null ? (
        <button className="secondary" style={{ marginTop: 4 }} onClick={() => setNewContact({ name: '', role: '', email: '', phone: '' })}>
          + Ajouter un contact
        </button>
      ) : (
        <div className="actions-row" style={{ marginTop: 6 }}>
          <input type="text" placeholder="Nom *" style={{ width: 140 }} value={newContact.name} onChange={(e) => setNewContact({ ...newContact, name: e.target.value })} />
          <input type="text" placeholder="Rôle" style={{ width: 130 }} value={newContact.role} onChange={(e) => setNewContact({ ...newContact, role: e.target.value })} />
          <input type="text" placeholder="Email" style={{ width: 180 }} value={newContact.email} onChange={(e) => setNewContact({ ...newContact, email: e.target.value })} />
          <input type="text" placeholder="Téléphone" style={{ width: 120 }} value={newContact.phone} onChange={(e) => setNewContact({ ...newContact, phone: e.target.value })} />
          <button
            className="primary"
            onClick={async () => {
              try {
                await api.addContact({ company, ...newContact })
                setNewContact(null)
                load()
                showToast('Contact ajouté.')
              } catch (err) { showToast(err.message, true) }
            }}
          >OK</button>
          <button className="secondary" onClick={() => setNewContact(null)}>Annuler</button>
        </div>
      )}
    </>
  )
}
