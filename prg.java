 public class program8 {
    public static void main(String[] args) {
        double accBal = 10000.0;
        int amount = 5000;
        if(amount <= accBal){
            System.out.println("Transaction successful");
        }
        else{
            System.out.println("Insufficient balance");
        }
    }
}