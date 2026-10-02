package main

import (
	"fmt"

	"example.com/svc/internal/auth"
)

func main() {
	fmt.Println(auth.Token())
}
