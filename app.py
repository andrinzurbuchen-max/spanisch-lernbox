import streamlit as st
import pandas as pd
from datetime import datetime
from openai import OpenAI
import json
import random
from supabase import create_client, Client

# ====================== SEITEN-EINSTELLUNGEN ======================
st.set_page_config(
    page_title="Spanisch Lernbox",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ====================== SESSION STATE ======================
if "vocab" not in st.session_state:
    st.session_state.vocab = []          # Liste mit Wörterbüchern

if "translation_result" not in st.session_state:
    st.session_state.translation_result = None

# ====================== SUPABASE + OPENAI ======================
supabase: Client = create_client(
    st.secrets["supabase"]["url"],
    st.secrets["supabase"]["key"]
)

api_key = None
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    pass

if not api_key:
    api_key = st.sidebar.text_input("OpenAI API Key", type="password")

if not api_key:
    st.warning("Bitte gib deinen OpenAI API-Key ein.")
    st.stop()

client = OpenAI(api_key=api_key)

# Wörter aus Supabase laden (beim Start der App)
def load_vocab_from_supabase():
    try:
        response = supabase.table("vocab").select("*").order("id").execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Fehler beim Laden aus Supabase: {e}")
        return []

# Beim ersten Laden die Wörter holen
if "vocab_loaded" not in st.session_state:
    st.session_state.vocab = load_vocab_from_supabase()
    st.session_state.vocab_loaded = True
# ====================== HILFSFUNKTIONEN ======================
def translate_word(word: str):
    """Holt korrigierte Schreibweise + Übersetzung + Alternativen von OpenAI"""
    
    prompt = f"""
Du bist ein erfahrener Spanisch-Lehrer für Deutschsprachige.

Das eingegebene Wort/Ausdruck ist: "{word}"

Aufgabe:
1. Prüfe, ob das Wort richtig geschrieben ist. Falls es falsch geschrieben ist, korrigiere es.
2. Gib die beste deutsche Übersetzung und Alternativen.

Antworte **ausschließlich** mit einem gültigen JSON in diesem Format:

{{
  "corrected": "die korrekt geschriebene spanische Version",
  "was_corrected": true/false,
  "main": "die natürlichste und häufigste deutsche Übersetzung",
  "alternatives": [
    {{"translation": "Alternative 1", "note": "kurze Erklärung wann man das benutzt"}},
    {{"translation": "Alternative 2", "note": "kurze Erklärung"}},
    {{"translation": "Alternative 3", "note": "kurze Erklärung"}}
  ],
  "examples": [
    {{"es": "Beispielsatz auf Spanisch", "de": "Deutsche Übersetzung"}},
    {{"es": "Zweiter Beispielsatz", "de": "Deutsche Übersetzung"}}
  ]
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Du antwortest immer nur mit validem JSON."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.2
    )
    
    return json.loads(response.choices[0].message.content)

def add_to_vocab(spanish: str, german: str):
    """Fügt ein Wort zur Lernbox hinzu (Supabase + Session)"""
    # Prüfen ob schon vorhanden
    for item in st.session_state.vocab:
        if item["spanish"].lower() == spanish.lower():
            return False

    new_item = {
        "spanish": spanish.strip(),
        "german": german.strip(),
        "added": datetime.now().strftime("%d.%m.%Y %H:%M")
    }

    # In Supabase speichern
    try:
        result = supabase.table("vocab").insert(new_item).execute()
        # Die von Supabase generierte id übernehmen
        if result.data:
            new_item["id"] = result.data[0]["id"]
    except Exception as e:
        st.error(f"Fehler beim Speichern in Supabase: {e}")
        return False

    st.session_state.vocab.append(new_item)
    return True

# ====================== APP ======================
st.title("📚 Spanisch Lernbox")
st.caption("Neue Wörter übersetzen und systematisch lernen")

tab1, tab2, tab3 = st.tabs(["Neues Wort", "Lernbox", "Quiz"])

# ---------------------- TAB 1: NEUES WORT ----------------------
with tab1:
    st.subheader("Neues Wort übersetzen")
    
    word = st.text_input(
        "Spanisches Wort oder Ausdruck",
        placeholder="z.B. aprovechar, echar de menos, por cierto...",
        key="word_input"
    )
    
    col1, col2 = st.columns([1, 3])
    with col1:
        translate_btn = st.button("Übersetzen", type="primary", use_container_width=True)
    
    if translate_btn and word.strip():
        with st.spinner("Übersetze..."):
            try:
                result = translate_word(word.strip())
                st.session_state.translation_result = {
                    "original": word.strip(),
                    "data": result
                }
            except Exception as e:
                st.error(f"Fehler bei der Übersetzung: {e}")
                st.session_state.translation_result = None

    # Ergebnis anzeigen
    if st.session_state.translation_result:
        data = st.session_state.translation_result["data"]
        original = st.session_state.translation_result["original"]
        
        st.divider()
        
        # Zeige Korrektur an, falls nötig
        if data.get("was_corrected"):
            st.warning(f"Du hast „{original}“ geschrieben. Gemeint war wahrscheinlich: **{data['corrected']}**")
            display_word = data["corrected"]
        else:
            display_word = original
            st.markdown(f"### Ergebnis für: **{display_word}**")
        
        st.success(f"**Hauptübersetzung:** {data['main']}")
        
        st.markdown("**Alternativen:**")
        for alt in data.get("alternatives", []):
            st.markdown(f"- **{alt['translation']}** — {alt['note']}")
        
        with st.expander("Beispielsätze anzeigen"):
            for ex in data.get("examples", []):
                st.markdown(f"- *{ex['es']}*  \n  → {ex['de']}")
        
        st.divider()
        st.markdown("### In die Lernbox speichern")
        
        options = [data["main"]] + [a["translation"] for a in data.get("alternatives", [])]
        
        selected = st.radio(
            "Welche Übersetzung soll in die Lernbox?",
            options=options,
            index=0
        )
        
        if st.button("In Lernbox speichern", type="primary"):
            # Immer die korrigierte Version speichern
            success = add_to_vocab(data["corrected"], selected)
            if success:
                st.success(f"„{data['corrected']} → {selected}“ wurde gespeichert!")
                st.session_state.translation_result = None
                st.rerun()
            else:
                st.warning("Dieses Wort ist bereits in der Lernbox.")

# ---------------------- TAB 2: LERNBOX ----------------------
with tab2:
    st.subheader(f"Deine Lernbox ({len(st.session_state.vocab)} Wörter)")
    
    if not st.session_state.vocab:
        st.info("Noch keine Wörter gespeichert. Gehe zu „Neues Wort“.")
    else:
        df = pd.DataFrame(st.session_state.vocab)
        df = df[["spanish", "german", "added"]]
        df.columns = ["Spanisch", "Deutsch", "Hinzugefügt"]
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Löschen
        st.markdown("#### Wort löschen")
        to_delete = st.selectbox(
            "Wort auswählen zum Löschen",
            options=[f"{v['spanish']} → {v['german']}" for v in st.session_state.vocab],
            index=None,
            placeholder="Wort auswählen..."
        )
        
        if to_delete and st.button("Löschen", type="secondary"):
            idx = [f"{v['spanish']} → {v['german']}" for v in st.session_state.vocab].index(to_delete)
            word_to_delete = st.session_state.vocab[idx]
            
            # Aus Supabase löschen
            try:
                if "id" in word_to_delete:
                    supabase.table("vocab").delete().eq("id", word_to_delete["id"]).execute()
            except Exception as e:
                st.error(f"Fehler beim Löschen: {e}")
            
            st.session_state.vocab.pop(idx)
            st.rerun()
    
    st.divider()
    st.markdown("### Speichern & Laden")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        if st.session_state.vocab:
            csv = pd.DataFrame(st.session_state.vocab).to_csv(index=False).encode("utf-8")
            st.download_button(
                "CSV herunterladen",
                data=csv,
                file_name=f"lernbox_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col_b:
        uploaded = st.file_uploader("CSV hochladen", type=["csv"], label_visibility="collapsed")
        if uploaded:
            try:
                new_df = pd.read_csv(uploaded)
                st.session_state.vocab = new_df.to_dict("records")
                st.success("Lernbox geladen!")
                st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Laden: {e}")

# ---------------------- TAB 3: QUIZ ----------------------
with tab3:
    st.subheader("Quiz")

    if len(st.session_state.vocab) == 0:
        st.info("Noch keine Wörter in der Lernbox. Füge zuerst Wörter hinzu.")
        st.stop()

    if len(st.session_state.vocab) < 4:
        st.warning("Für Multiple Choice brauchst du mindestens 4 Wörter. Flashcards funktionieren trotzdem.")

    # Quiz-Einstellungen
    mode = st.radio("Modus wählen", ["Flashcards", "Multiple Choice"], horizontal=True)

    # Session State fürs Quiz initialisieren
    if "quiz_started" not in st.session_state:
        st.session_state.quiz_started = False
        st.session_state.quiz_index = 0
        st.session_state.quiz_score = 0
        st.session_state.quiz_order = []
        st.session_state.show_answer = False
        st.session_state.answered = False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Quiz starten / Neu starten", type="primary", use_container_width=True):
            st.session_state.quiz_started = True
            st.session_state.quiz_index = 0
            st.session_state.quiz_score = 0
            st.session_state.quiz_order = list(range(len(st.session_state.vocab)))
            random.shuffle(st.session_state.quiz_order)
            st.session_state.show_answer = False
            st.session_state.answered = False
            st.rerun()

    with col2:
        if st.session_state.quiz_started:
            st.metric("Punktestand", f"{st.session_state.quiz_score} / {st.session_state.quiz_index}")

    if not st.session_state.quiz_started:
        st.info("Klicke auf **Quiz starten**, um zu beginnen.")
        st.stop()

    # Aktuelles Wort holen
    if st.session_state.quiz_index >= len(st.session_state.quiz_order):
        st.success(f"Quiz beendet! Du hast {st.session_state.quiz_score} von {len(st.session_state.quiz_order)} richtig.")
        if st.button("Nochmal spielen"):
            st.session_state.quiz_started = False
            st.rerun()
        st.stop()

    current_idx = st.session_state.quiz_order[st.session_state.quiz_index]
    current_word = st.session_state.vocab[current_idx]

    st.divider()
    st.markdown(f"### Wort {st.session_state.quiz_index + 1} von {len(st.session_state.quiz_order)}")
    st.markdown(f"## {current_word['spanish']}")

    # ========== FLASHCARDS ==========
    if mode == "Flashcards":
        if not st.session_state.show_answer:
            if st.button("Antwort zeigen", use_container_width=True):
                st.session_state.show_answer = True
                st.rerun()
        else:
            st.success(f"**{current_word['german']}**")
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Richtig", use_container_width=True):
                    st.session_state.quiz_score += 1
                    st.session_state.quiz_index += 1
                    st.session_state.show_answer = False
                    st.rerun()
            with col_b:
                if st.button("Falsch", use_container_width=True):
                    st.session_state.quiz_index += 1
                    st.session_state.show_answer = False
                    st.rerun()

    # ========== MULTIPLE CHOICE ==========
    else:
        if st.session_state.answered:
            st.info("Klicke auf **Nächstes Wort**")
            if st.button("Nächstes Wort", type="primary"):
                st.session_state.quiz_index += 1
                st.session_state.answered = False
                st.rerun()
        else:
            # Falsche Antworten generieren
            all_germans = [w["german"] for w in st.session_state.vocab]
            correct = current_word["german"]
            
            wrong_options = [g for g in all_germans if g != correct]
            random.shuffle(wrong_options)
            options = wrong_options[:3] + [correct]
            random.shuffle(options)

            selected = st.radio("Was bedeutet das?", options, index=None)

            if selected:
                if selected == correct:
                    st.success("Richtig!")
                    st.session_state.quiz_score += 1
                else:
                    st.error(f"Falsch. Richtig ist: **{correct}**")
                
                st.session_state.answered = True
                st.rerun()

# ====================== FUSSZEILE ======================
st.divider()
st.caption("Persönliche Spanisch-Lernbox • gebaut mit Streamlit + OpenAI")
 # ========== TEST SUPABASE (später wieder löschen) ==========
st.divider()
st.subheader("Supabase Test")

if st.button("Test: Wort in Supabase speichern"):
    try:
        test_data = {
            "spanish": "testwort",
            "german": "Test",
            "added": "27.07.2026"
        }
        result = supabase.table("vocab").insert(test_data).execute()
        st.success("Erfolgreich gespeichert!")
        st.write(result.data)
    except Exception as e:
        st.error("Fehler:")
        st.exception(e)
