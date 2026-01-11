test_text = "/cambiar: QA x2"
print(f"Text: {repr(test_text)}")
print(f"Lower: {repr(test_text.lower())}")
print(f"Starts with /cambiar: {test_text.lower().startswith('/cambiar:')}")

if test_text.lower().startswith("/cambiar:"):
    arg = test_text.split(":", 1)[1].strip()
    print(f"Arg: {repr(arg)}")
